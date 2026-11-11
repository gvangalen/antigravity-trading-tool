"""Prepare only the bound FINN QA owner's genuine manual-trade evidence.

This is a protected runner profile, never an application endpoint. It leaves
existing setups and shared market rows untouched and fails closed on drift.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from sqlalchemy import text

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG
from backend.services.indicator_config_service import IndicatorConfigService
from backend.services.setup_service import SetupService


MARKER = "finn_manual_trade_qa_v1"
PROFILE = {
    "trader_types": ["swing_trader"],
    "primary_timeframes": ["1d"],
    "asset_focus": ["bitcoin", "crypto_general", "stocks"],
    "experience_levels": ["intermediate"],
    "risk_profiles": ["balanced"],
}
PAIRS = (("BTC", "EUR"), ("ETH", "USDT"), ("AAPL", "USD"))
INDICATORS = (("macro", "dxy"), ("technical", "rsi"), ("market", "change_24h"))
LOCK_NAMESPACE = 0x464D5451


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def _journal(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise RuntimeError("manual_trade_journal_path_invalid")
    fd, temporary = tempfile.mkstemp(prefix=".manual-trade-qa-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


async def _owner_and_safety(session, owner: int) -> dict[str, Any]:
    row = (await session.execute(text("""
        SELECT role,is_active,ai_preferences FROM users WHERE id=:owner FOR UPDATE
    """), {"owner": owner})).mappings().one_or_none()
    if (row is None or row["role"] != "user" or row["is_active"] is not True
            or not isinstance(row["ai_preferences"], dict)
            or row["ai_preferences"].get("qa_fixture") != "finn_production_qa_v1"):
        raise RuntimeError("manual_trade_fixture_owner_invalid")
    safety = (await session.execute(text("""
        SELECT
          (SELECT count(*) FROM exchange_keys WHERE user_id=:owner) AS keys,
          (SELECT count(*) FROM bot_orders WHERE user_id=:owner) AS orders,
          (SELECT count(*) FROM bot_configs WHERE user_id=:owner AND COALESCE(is_live,false)) AS live_bots,
          (SELECT count(*) FROM bot_configs WHERE user_id=:owner AND COALESCE(is_active,false)) AS active_bots,
          (SELECT count(*) FROM finn_v2_proposals WHERE user_id=:owner
             AND status IN ('draft','pending_confirmation','confirmed')
             AND expires_at>CURRENT_TIMESTAMP) AS pending,
          (SELECT count(*) FROM finn_manual_trade_plans
             WHERE user_id=:owner AND plan_json->>'executable' IS DISTINCT FROM 'false') AS unsafe_plans
    """), {"owner": owner})).mappings().one()
    if any(int(safety[key]) for key in ("keys", "orders", "live_bots", "active_bots", "pending", "unsafe_plans")):
        raise RuntimeError("manual_trade_fixture_owner_unsafe")
    return dict(row["ai_preferences"])


async def _btc_setup_state(session, owner: int, market_id: int) -> str:
    rows = (await session.execute(text("""
        SELECT to_jsonb(s) AS state FROM setups s
        WHERE s.user_id=:owner AND s.symbol='BTC' AND s.market_id=:market_id
          AND s.description IS DISTINCT FROM :marker
        ORDER BY s.id
    """), {"owner": owner, "market_id": market_id,
           "marker": MARKER})).scalars().all()
    if len(rows) != 2:
        raise RuntimeError("manual_trade_btc_setup_baseline_changed")
    strategies = (await session.execute(text("""
        SELECT to_jsonb(st) AS state FROM strategies st
        JOIN setups s ON s.id=st.setup_id
        WHERE s.user_id=:owner AND s.symbol='BTC' AND s.market_id=:market_id
          AND s.description IS DISTINCT FROM :marker
        ORDER BY st.id
    """), {"owner": owner, "market_id": market_id,
           "marker": MARKER})).scalars().all()
    bots = (await session.execute(text("""
        SELECT to_jsonb(b) AS state FROM bot_configs b
        JOIN strategies st ON st.id=b.strategy_id
        JOIN setups s ON s.id=st.setup_id
        WHERE s.user_id=:owner AND s.symbol='BTC' AND s.market_id=:market_id
          AND s.description IS DISTINCT FROM :marker
        ORDER BY b.id
    """), {"owner": owner, "market_id": market_id,
           "marker": MARKER})).scalars().all()
    return _digest({"setups": rows, "strategies": strategies, "bots": bots})


async def _markets(session) -> dict[str, int | None]:
    result = {"AAPL": None}
    if (DEFAULT_ASSET_CATALOG.get("AAPL") or {}).get("quote_currency") != "USD":
        raise RuntimeError("manual_trade_stock_catalog_changed")
    for asset, quote in PAIRS[:2]:
        rows = (await session.execute(text("""
            SELECT id FROM trading_markets
            WHERE asset_symbol=:asset AND quote_currency=:quote
              AND venue='BINANCE' AND provider='binance'
              AND provider_symbol=:provider_symbol
              AND tradingview_symbol=:tradingview_symbol
              AND is_active=TRUE
        """), {"asset": asset, "quote": quote,
               "provider_symbol": f"{asset}{quote}",
               "tradingview_symbol": f"BINANCE:{asset}{quote}"})).scalars().all()
        if len(rows) != 1:
            raise RuntimeError("manual_trade_exact_market_unavailable")
        result[asset] = int(rows[0])
    return result


async def _no_other_pair_evidence(session, owner: int,
                                  markets: dict[str, int | None]) -> None:
    """Asset-scoped macro refresh must not invalidate another quote's score."""
    for asset in ("BTC", "ETH"):
        count = (await session.execute(text("""
            SELECT
              (SELECT count(*) FROM user_indicator_configs
               WHERE user_id=:owner AND symbol=:asset
                 AND market_id IS DISTINCT FROM :market_id) AS configs,
              (SELECT count(*) FROM daily_scores
               WHERE user_id=:owner AND symbol=:asset
                 AND market_id IS DISTINCT FROM :market_id) AS scores
        """), {"owner": owner, "asset": asset,
               "market_id": markets[asset]})).mappings().one()
        if int(count["configs"]) or int(count["scores"]):
            raise RuntimeError("manual_trade_other_pair_evidence_present")


async def _source_preflight() -> None:
    """Require real current plan sources before the first fixture write."""
    from backend.services.finn_manual_trade_suggestion_service import (
        _source_candles, derive_suggested_plan,
    )

    async with async_session_factory() as session:
        for asset, quote in PAIRS:
            if asset == "AAPL":
                await session.rollback()
            market_id, candles = await _source_candles(
                session, asset=asset, quote_currency=quote)
            derive_suggested_plan(
                asset=asset, quote_currency=quote, direction="long",
                max_loss_quote="20", candles=candles, market_id=market_id)
        await session.rollback()


async def _setup(session, owner: int, asset: str, quote: str,
                 market_id: int | None,
                 band: list[int] | None = None) -> tuple[int, bool]:
    name = f"FINN QA manual trade {asset}/{quote}"
    payload = {
        "name": name, "symbol": asset, "market_id": market_id,
        "timeframe": "1d", "setup_type": "trade",
        "min_benchmark_score": (band or [0, 100])[0],
        "max_benchmark_score": (band or [0, 100])[1],
        "description": MARKER, "explanation": MARKER,
    }
    SetupService(session).validate_setup_payload(dict(payload))
    rows = (await session.execute(text("""
        SELECT to_jsonb(s) AS state
        FROM setups s WHERE user_id=:owner AND symbol=:asset
          AND ((CAST(:market_id AS BIGINT) IS NULL AND market_id IS NULL)
               OR market_id=:market_id)
          AND lower(setup_type)='trade'
    """), {"owner": owner, "asset": asset,
           "market_id": market_id})).mappings().all()
    rows = [row["state"] for row in rows]
    if asset == "BTC":
        marked = [row for row in rows if row["description"] == MARKER]
        if len(marked) > 1 or len(rows) - len(marked) != 2:
            raise RuntimeError("manual_trade_target_setup_ambiguous")
    else:
        marked = rows
        if len(rows) > 1:
            raise RuntimeError("manual_trade_target_setup_ambiguous")
    if marked:
        row = marked[0]
        expected = {
            "user_id": owner, "name": name, "symbol": asset,
            "market_id": market_id, "timeframe": "1d", "setup_type": "trade",
            "dca_frequency": None, "dca_day": None, "dca_month_day": None,
            "account_type": None, "min_investment": None, "tags": [MARKER],
            "trend": None, "score_logic": None, "favorite": False,
            "explanation": MARKER, "description": MARKER,
            "action": None, "category": None,
            "min_macro_score": None, "max_macro_score": None,
            "min_technical_score": None, "max_technical_score": None,
            "min_market_score": None, "max_market_score": None,
            "min_benchmark_score": payload["min_benchmark_score"],
            "max_benchmark_score": payload["max_benchmark_score"],
        }
        if any(row.get(key) != value for key, value in expected.items()):
            raise RuntimeError("manual_trade_target_setup_drift")
        return int(row["id"]), False
    created = await SetupRepository(session).create_setup(payload, owner, [MARKER])
    if type(created) is not int or created <= 0:
        raise RuntimeError("manual_trade_target_setup_create_failed")
    return created, True


async def _config(session, owner: int, asset: str,
                  market_id: int | None, category: str, indicator: str) -> bool:
    rows = (await session.execute(text("""
        SELECT id,indicator,enabled,provenance,config_json,priority
        FROM user_indicator_configs
        WHERE user_id=:owner AND symbol=:asset AND category=:category
          AND ((CAST(:market_id AS BIGINT) IS NULL AND market_id IS NULL)
               OR market_id=:market_id)
    """), {"owner": owner, "asset": asset, "category": category,
           "market_id": market_id})).mappings().all()
    expected = {"score_mode": "standard", "weight": 1.0}
    if rows:
        if len(rows) != 1 or rows[0]["indicator"].lower() != indicator:
            raise RuntimeError("manual_trade_indicator_config_drift")
        row = rows[0]
        if (row["enabled"] is not True or row["provenance"] != MARKER
                or row["config_json"] != expected or int(row["priority"]) != 100):
            raise RuntimeError("manual_trade_indicator_config_drift")
        return False
    await session.execute(text("""
        INSERT INTO user_indicator_configs
          (user_id,indicator,category,symbol,market_id,asset_class,
           priority,enabled,config_json,provenance,created_at,updated_at)
        VALUES (:owner,:indicator,:category,:asset,:market_id,:asset_class,
                100,TRUE,CAST(:config AS json),:marker,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    """), {"owner": owner, "indicator": indicator, "category": category,
           "asset": asset, "market_id": market_id,
           "asset_class": "stock" if asset == "AAPL" else "crypto",
           "config": json.dumps(expected), "marker": MARKER})
    return True


async def _aapl_reading_scope(session, owner: int) -> int | None:
    """Only a reading bound to this marked config may survive a retry."""
    rows = (await session.execute(text("""
        SELECT id FROM market_data_indicators
        WHERE user_id=:owner AND symbol='AAPL' AND name='change_24h'
          AND market_id IS NULL
        ORDER BY id
    """), {"owner": owner})).scalars().all()
    config = (await session.execute(text("""
        SELECT provenance,source_record_id FROM user_indicator_configs
        WHERE user_id=:owner AND symbol='AAPL' AND category='market'
          AND indicator='change_24h' AND market_id IS NULL
    """), {"owner": owner})).mappings().one()
    if not rows:
        if config["source_record_id"] is not None:
            raise RuntimeError("manual_trade_aapl_reading_drift")
        return None
    if (len(rows) != 1 or config["provenance"] != MARKER
            or config["source_record_id"] != rows[0]):
        raise RuntimeError("manual_trade_aapl_reading_unowned")
    return int(rows[0])


async def configure_bound_fixture(owner: int) -> dict[str, Any]:
    """One bounded owner-locked transaction for profile, setups and choices."""
    async with async_session_factory() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:ns,:owner)"),
                              {"ns": LOCK_NAMESPACE, "owner": owner})
        preferences = await _owner_and_safety(session, owner)
        markets = await _markets(session)
        await _no_other_pair_evidence(session, owner, markets)
        baseline = await _btc_setup_state(session, owner, markets["BTC"])
        from backend.services.trader_profile_service import normalize_trader_profile_preferences
        current = normalize_trader_profile_preferences(preferences)
        if not any(current.values()):
            preferences.update(PROFILE)
            preferences["manual_trade_qa_profile"] = MARKER
            await session.execute(text("""
                UPDATE users SET ai_preferences=CAST(:preferences AS jsonb)
                WHERE id=:owner
            """), {"owner": owner, "preferences": json.dumps(preferences)})
            profile_created = True
        elif (preferences.get("manual_trade_qa_profile") == MARKER
              and all(preferences.get(key) == value for key, value in PROFILE.items())):
            profile_created = False
        else:
            raise RuntimeError("manual_trade_profile_drift")
        for category, indicator in INDICATORS:
            rules = await IndicatorConfigRepository(session).get_system_indicator_rules(
                category, indicator)
            if not IndicatorConfigService._has_complete_rules(rules):
                raise RuntimeError("manual_trade_scoring_rules_unavailable")
        setups_created = 0
        bands = preferences.get("manual_trade_qa_bands") or {}
        if bands and (not isinstance(bands, dict)
                      or set(bands) != {"ETH", "AAPL"}
                      or any(not isinstance(band, list) or len(band) != 2
                             or not all(type(x) is int and 0 <= x <= 100 for x in band)
                             or band[0] > band[1] for band in bands.values())):
            raise RuntimeError("manual_trade_scenario_bands_drift")
        for asset, quote in PAIRS:
            _, created = await _setup(session, owner, asset, quote, markets[asset],
                                      bands.get(asset))
            setups_created += int(created)
        configs_created = 0
        for asset, _ in PAIRS:
            for category, indicator in INDICATORS:
                configs_created += int(await _config(
                    session, owner, asset, markets[asset], category, indicator))
        await _aapl_reading_scope(session, owner)
        for asset in ("BTC", "ETH"):
            weights = (await session.execute(text("""
                SELECT weights,indicators_isolated FROM user_market_benchmark_weights
                WHERE user_id=:owner AND market_id=:market_id
            """), {"owner": owner, "market_id": markets[asset]})).mappings().one_or_none()
            expected = {"macro": 1 / 3, "technical": 1 / 3, "market": 1 / 3}
            if weights is None:
                await session.execute(text("""
                    INSERT INTO user_market_benchmark_weights
                      (user_id,market_id,weights,indicators_isolated,updated_at)
                    VALUES (:owner,:market_id,CAST(:weights AS jsonb),TRUE,CURRENT_TIMESTAMP)
                """), {"owner": owner, "market_id": markets[asset],
                       "weights": json.dumps(expected)})
            elif (weights["indicators_isolated"] is not True
                  or weights["weights"] != expected):
                raise RuntimeError("manual_trade_pair_weights_drift")
        if await _btc_setup_state(session, owner, markets["BTC"]) != baseline:
            raise RuntimeError("manual_trade_btc_setup_changed")
        await session.commit()
    return {"markets": markets, "btc_setup_hash": baseline,
            "profile_created": profile_created,
            "setups_created": setups_created, "configs_created": configs_created}


async def refresh_genuine_sources(owner: int, markets: dict[str, int | None]) -> dict[str, Any]:
    """Use normal provider and exact-pair materializers, never supplied values."""
    from backend.celery_task.store_daily_scores_task import (
        build_daily_scores_for_market, build_daily_scores_for_user,
    )
    from backend.services.exact_market_indicator_service import ExactMarketIndicatorService
    from backend.services.indicator_history_bootstrap import IndicatorHistoryBootstrap
    from backend.services.macro_data_service import MacroDataService
    from backend.services.market_data_service import MarketDataService
    from backend.services.pair_indicator_config_service import PairIndicatorConfigService
    from backend.services.technical_data_service import TechnicalDataService

    result: dict[str, Any] = {}
    for asset, _ in PAIRS:
        async with async_session_factory() as session:
            history = await IndicatorHistoryBootstrap(session).bootstrap_macro(
                owner, "dxy", asset)
            if history.get("status") != "ready":
                raise RuntimeError("manual_trade_macro_history_unavailable")
            macro = await MacroDataService(session).sync_effective_indicators(
                owner, asset, indicator_names_override=["dxy"])
            if macro.get("failed") or len(macro.get("synced") or []) != 1:
                raise RuntimeError("manual_trade_macro_source_unavailable")
            if asset == "AAPL":
                technical = await TechnicalDataService(session).sync_effective_indicators(
                    owner, asset, explicit_indicators=["rsi"],
                    persist_preferences=False)
                if technical.get("failed") or len(technical.get("synced") or []) != 1:
                    raise RuntimeError("manual_trade_technical_source_unavailable")
                existing_reading = await _aapl_reading_scope(session, owner)
                if existing_reading is None:
                    # The provider's catalog lookup uses a second session;
                    # release the read transaction before that bounded call.
                    await session.rollback()
                    saved = await MarketDataService(session).add_user_market_indicator(
                        owner, "change_24h", None, symbol=asset,
                        persist_preference=False, refresh_existing=False,
                        prefer_live_snapshot=True, commit=False)
                    linked = await session.execute(text("""
                        UPDATE user_indicator_configs SET source_record_id=:record_id,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE user_id=:owner AND symbol='AAPL' AND category='market'
                          AND indicator='change_24h' AND market_id IS NULL
                          AND provenance=:marker AND source_record_id IS NULL
                    """), {"record_id": saved.id, "owner": owner, "marker": MARKER})
                    if linked.rowcount != 1:
                        raise RuntimeError("manual_trade_aapl_reading_link_failed")
                    await session.commit()
                    if await _aapl_reading_scope(session, owner) != saved.id:
                        raise RuntimeError("manual_trade_aapl_reading_link_failed")
                await session.rollback()
                await asyncio.to_thread(build_daily_scores_for_user,
                                        owner, [asset], publish_feed=False)
                result[asset] = {"macro_history_ready": True,
                                 "market_and_technical_materialized": True}
            else:
                market = await PairIndicatorConfigService(session).market(
                    int(markets[asset]))
                if market is None or market.asset_symbol != asset:
                    raise RuntimeError("manual_trade_exact_market_unavailable")
                materialized = await ExactMarketIndicatorService(session).materialize(
                    market, owner_ids={owner}, only_owner=True)
                if materialized.get("written", 0) < 2:
                    raise RuntimeError("manual_trade_pair_sources_unavailable")
                await session.rollback()
                score = await asyncio.to_thread(build_daily_scores_for_market,
                                                owner, int(markets[asset]))
                if any(score["scores"].get(category) is None
                       for category in ("macro", "technical", "market")):
                    raise RuntimeError("manual_trade_pair_scores_incomplete")
                result[asset] = {"macro_history_ready": True,
                                 "market_and_technical_materialized": True}
    return result


def _scenario_band(score: float, recommendation: str) -> list[int]:
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise RuntimeError("manual_trade_benchmark_score_invalid")
    if recommendation == "reduced_risk":
        return ([math.ceil(score + 1), 100] if score <= 98
                else [0, math.floor(score - 1)])
    if recommendation == "wait":
        return [100, 100] if score <= 50 else [0, 0]
    raise RuntimeError("manual_trade_scenario_invalid")


async def set_verified_scenarios(owner: int, expected: dict[str, Any]) -> dict[str, str]:
    """Derive QA mismatch bands from genuine scores, never fabricated scores."""
    from backend.services.setup_market_match_service import SetupMarketMatchService

    async with async_session_factory() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:ns,:owner)"),
                              {"ns": LOCK_NAMESPACE, "owner": owner})
        preferences = await _owner_and_safety(session, owner)
        markets = await _markets(session)
        if markets != expected["markets"]:
            raise RuntimeError("manual_trade_market_identity_changed")
        if await _btc_setup_state(session, owner, int(markets["BTC"])) != expected["btc_setup_hash"]:
            raise RuntimeError("manual_trade_btc_setup_changed")
        old_bands = preferences.get("manual_trade_qa_bands") or {}
        new_bands = {}
        for asset, desired in (("ETH", "reduced_risk"), ("AAPL", "wait")):
            assessment = await SetupMarketMatchService(session).for_asset(
                owner, asset, setups=[], market_id=markets[asset])
            if (assessment.get("source_status") != "available"
                    or assessment.get("benchmark_score") is None
                    or any(assessment.get("component_source_status", {}).get(f"{category}_score") != "fresh"
                           for category in ("macro", "technical", "market"))):
                raise RuntimeError("manual_trade_verified_score_unavailable")
            band = _scenario_band(float(assessment["benchmark_score"]), desired)
            new_bands[asset] = band
            setup_id, _ = await _setup(session, owner, asset,
                                       "USDT" if asset == "ETH" else "USD",
                                       markets[asset], old_bands.get(asset))
            changed = await session.execute(text("""
                UPDATE setups SET min_benchmark_score=:minimum,
                                  max_benchmark_score=:maximum
                WHERE id=:setup_id AND user_id=:owner AND description=:marker
                  AND min_benchmark_score=:old_minimum
                  AND max_benchmark_score=:old_maximum
            """), {"minimum": band[0], "maximum": band[1],
                   "old_minimum": (old_bands.get(asset) or [0, 100])[0],
                   "old_maximum": (old_bands.get(asset) or [0, 100])[1],
                   "setup_id": setup_id, "owner": owner, "marker": MARKER})
            if changed.rowcount != 1:
                raise RuntimeError("manual_trade_scenario_setup_cas_failed")
        preferences["manual_trade_qa_bands"] = new_bands
        await session.execute(text("""
            UPDATE users SET ai_preferences=CAST(:preferences AS jsonb)
            WHERE id=:owner
        """), {"owner": owner, "preferences": json.dumps(preferences)})
        await session.commit()
    return {"BTC": "review", "ETH": "reduced_risk", "AAPL": "wait"}


async def verify_bound_fixture(owner: int, expected: dict[str, Any]) -> dict[str, Any]:
    from backend.services.finn_manual_trade_suggestion_service import _owner_trade_context
    from backend.services.setup_market_match_service import SetupMarketMatchService

    async with async_session_factory() as session:
        preferences = await _owner_and_safety(session, owner)
        if preferences.get("manual_trade_qa_profile") != MARKER:
            raise RuntimeError("manual_trade_profile_drift")
        markets = await _markets(session)
        await _no_other_pair_evidence(session, owner, markets)
        if await _aapl_reading_scope(session, owner) is None:
            raise RuntimeError("manual_trade_aapl_reading_missing")
        if markets != expected["markets"]:
            raise RuntimeError("manual_trade_market_identity_changed")
        if await _btc_setup_state(session, owner, int(markets["BTC"])) != expected["btc_setup_hash"]:
            raise RuntimeError("manual_trade_btc_setup_changed")
        verified = {}
        for asset, quote in PAIRS:
            name = f"FINN QA manual trade {asset}/{quote}"
            row = (await session.execute(text("""
                SELECT id FROM setups
                WHERE user_id=:owner AND name=:name AND symbol=:asset
                  AND ((CAST(:market_id AS BIGINT) IS NULL AND market_id IS NULL)
                       OR market_id=:market_id)
            """), {"owner": owner, "name": name, "asset": asset,
                   "market_id": markets[asset]})).scalars().one_or_none()
            if row is None:
                raise RuntimeError("manual_trade_target_setup_missing")
            setup_id = int(row)
            context = await _owner_trade_context(
                session, user_id=owner, asset=asset, quote_currency=quote,
                market_id=markets[asset], selected_setup_id=setup_id)
            assessment = await SetupMarketMatchService(session).for_asset(
                owner, asset, setups=[], market_id=markets[asset])
            if (assessment.get("source_status") != "available"
                    or assessment.get("benchmark_score") is None
                    or any(assessment.get("component_source_status", {}).get(f"{category}_score") != "fresh"
                           for category in ("macro", "technical", "market"))):
                raise RuntimeError("manual_trade_verified_score_unavailable")
            expected_recommendation = {"BTC": "review", "ETH": "reduced_risk", "AAPL": "wait"}[asset]
            if context.get("recommendation") != expected_recommendation:
                raise RuntimeError("manual_trade_qa_setup_not_matched")
            if asset in {"ETH", "AAPL"} and context.get("risk_factor") != "0.5":
                raise RuntimeError("manual_trade_qa_risk_factor_invalid")
            if asset == "AAPL" and context.get("reason") != "manual_trade_setup_outside_conditions":
                raise RuntimeError("manual_trade_qa_wait_reason_invalid")
            verified[asset] = {"quote": quote, "score_verified": True,
                               "qa_setup_matched": True,
                               "recommendation": expected_recommendation}
        await session.rollback()
    return verified


async def run(*, journal_path: Path, release_sha: str,
              fixture_namespace: str) -> dict[str, Any]:
    if os.getenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE") != "1":
        raise RuntimeError("manual_trade_fixture_not_authorized")
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise RuntimeError("manual_trade_release_sha_invalid")
    if not re.fullmatch(r"qa-[0-9]+-[0-9]+-[0-9a-f]{8}-[0-9a-f]{8}",
                        fixture_namespace):
        raise RuntimeError("manual_trade_fixture_namespace_invalid")
    raw = os.getenv("FINN_QA_USER_ID", "")
    if not raw.isdecimal() or int(raw) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    owner = int(raw)
    if journal_path.exists():
        if journal_path.is_symlink() or journal_path.stat().st_mode & 0o077:
            raise RuntimeError("manual_trade_journal_invalid")
        state = json.loads(journal_path.read_text())
        if (state.get("marker") != MARKER or state.get("owner") != owner
                or state.get("release_sha") != release_sha
                or state.get("namespace") != fixture_namespace):
            raise RuntimeError("manual_trade_journal_binding_changed")
        state["phase"] = "resumed"
    else:
        state = {"marker": MARKER, "owner": owner, "release_sha": release_sha,
                 "namespace": fixture_namespace,
                 "started_at": datetime.now(timezone.utc).isoformat(),
                 "phase": "started"}
    _journal(journal_path, state)
    try:
        await _source_preflight()
        state["phase"] = "sources_preflight_passed"
        _journal(journal_path, state)
        configured = await configure_bound_fixture(owner)
        state.update({"phase": "configured", "btc_setup_hash": configured["btc_setup_hash"],
                      "markets": configured["markets"],
                      "profile_created": configured["profile_created"],
                      "setups_created": configured["setups_created"],
                      "configs_created": configured["configs_created"]})
        _journal(journal_path, state)
        source = await refresh_genuine_sources(owner, configured["markets"])
        state.update({"phase": "sources_refreshed", "source_status": source})
        _journal(journal_path, state)
        scenarios = await set_verified_scenarios(owner, configured)
        state.update({"phase": "scenarios_configured", "scenarios": scenarios})
        _journal(journal_path, state)
        verified = await verify_bound_fixture(owner, configured)
        state.update({"phase": "verified", "verified": verified})
        _journal(journal_path, state)
        return {"status": "prepared", "profile_created": configured["profile_created"],
                "setups_created": configured["setups_created"],
                "configs_created": configured["configs_created"],
                "pairs": verified, "writes_performed": True,
                "broker_orders": 0, "live_bots": 0, "exchange_keys": 0}
    except Exception:
        state["phase"] = "failed"
        _journal(journal_path, state)
        raise
