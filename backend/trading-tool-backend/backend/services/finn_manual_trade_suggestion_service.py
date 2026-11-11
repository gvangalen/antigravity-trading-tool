"""Reproducible, non-executable manual trade levels from completed daily candles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import hmac
import json
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.domain.finn_manual_trade_plan_contract import _positive_decimal, validate_manual_trade_plan
from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG


METHOD_VERSION = "daily_tr_14_stop_1_5r_targets_1r_2r_v1"
ATTESTATION_LIFETIME = timedelta(minutes=10)
NEAR_MISS_POINTS = 3
REDUCED_RISK_FACTOR = Decimal("0.5")


class ManualTradeWait(ValueError):
    """A verified context says to wait instead of publishing a trade card."""


async def _owner_trade_context(session: Any, *, user_id: int, asset: str,
                               quote_currency: str, market_id: int | None) -> dict[str, Any]:
    from backend.infrastructure.repositories.setup_repository import SetupRepository
    from backend.infrastructure.repositories.user_repository import UserRepository
    from backend.services.setup_market_match_service import SetupMarketMatchService
    from backend.services.trader_profile_service import normalize_trader_profile_preferences

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise ManualTradeWait("manual_trade_profile_unavailable")
    profile = normalize_trader_profile_preferences(getattr(user, "ai_preferences", {}) or {})
    profile_hash = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()

    def wait(reason: str, setup: dict | None = None, assessment: dict | None = None) -> dict[str, Any]:
        return {
            "recommendation": "wait", "reason": reason,
            "risk_factor": str(REDUCED_RISK_FACTOR), "profile_hash": profile_hash,
            "setup_id": int(setup["id"]) if setup and setup.get("id") is not None else None,
            "setup_name": str(setup.get("name") or "") if setup else "",
            "setup_timeframe": str(setup.get("timeframe") or "") if setup else "",
            "benchmark_as_of": str((assessment or {}).get("as_of") or ""),
            "benchmark_score": (str(assessment["benchmark_score"])
                                if assessment and assessment.get("benchmark_score") is not None else ""),
            "setup_match_status": str((assessment or {}).get("source_status") or "unavailable"),
        }

    if not any(profile.values()):
        return wait("manual_trade_profile_missing")
    setups = [dict(row) for row in await SetupRepository(session).get_all_setups(user_id)]
    stock_without_market = market_id is None and (
        DEFAULT_ASSET_CATALOG.get(asset) or {}).get("asset_class") == "stock"
    candidates = [row for row in setups
                  if str(row.get("symbol") or "").upper() == asset
                  and row.get("market_id") == market_id
                  and (str(row.get("quote_currency") or "").upper() == quote_currency
                       or (stock_without_market and row.get("quote_currency") is None))
                  and str(row.get("setup_type") or "").lower() == "trade"]
    if not candidates:
        return wait("manual_trade_setup_missing")
    if len(candidates) != 1:
        return wait("manual_trade_setup_ambiguous")
    setup = candidates[0]
    timeframe = str(setup.get("timeframe") or "").lower()
    if timeframe not in {"1d", "1day"}:
        return wait("manual_trade_timeframe_source_unavailable", setup)
    preferred = set(profile.get("primary_timeframes") or [])
    trader_types = set(profile.get("trader_types") or [])
    if (preferred and "1d" not in preferred) or (not preferred and trader_types & {"day_trader", "scalper"}):
        return wait("manual_trade_profile_timeframe_conflict", setup)
    assessment = await SetupMarketMatchService(session).for_asset(
        user_id, asset, setups=[setup], market_id=market_id,
    )
    matches = assessment.get("matches") or []
    if (assessment.get("source_status") != "available"
            or assessment.get("benchmark_score") is None or len(matches) != 1):
        return wait("manual_trade_benchmark_unavailable", setup, assessment)
    match = matches[0]
    status = match.get("status")
    risk_profiles = set(profile.get("risk_profiles") or [])
    behavior_flags = set(profile.get("behavior_flags") or [])
    risk_factor = Decimal("1")
    recommendation = "review"
    if status == "matches":
        if "conservative" in risk_profiles or "beginner" in set(profile.get("experience_levels") or []):
            risk_factor = REDUCED_RISK_FACTOR
            recommendation = "reduced_risk"
    elif status == "outside_conditions":
        benchmark = (match.get("components") or {}).get("benchmark") or {}
        observed = benchmark.get("score")
        minimum = benchmark.get("minimum")
        maximum = benchmark.get("maximum")
        if observed is None:
            return wait("manual_trade_benchmark_unavailable", setup, assessment)
        gap = (float(minimum) - float(observed) if minimum is not None and observed < minimum
               else float(observed) - float(maximum) if maximum is not None and observed > maximum
               else 0)
        if (gap > NEAR_MISS_POINTS or "conservative" in risk_profiles
                or behavior_flags & {"fomo", "overtrades", "leverage_seeking"}):
            return wait("manual_trade_setup_outside_conditions", setup, assessment)
        risk_factor = REDUCED_RISK_FACTOR
        recommendation = "reduced_risk"
    else:
        return wait("manual_trade_setup_not_confirmed", setup, assessment)
    return {
        "setup_id": int(setup["id"]), "setup_name": str(setup.get("name") or ""),
        "setup_timeframe": timeframe, "benchmark_as_of": str(assessment.get("as_of") or ""),
        "benchmark_score": str(assessment["benchmark_score"]),
        "setup_match_status": str(status), "setup_match_score": str(match.get("score")),
        "risk_factor": str(risk_factor), "profile_hash": profile_hash,
        "recommendation": recommendation, "reason": "",
    }


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _attestation_digest(plan: dict[str, Any], user_id: int) -> str:
    from backend.utils.auth_utils import SECRET_KEY

    unsigned = json.loads(json.dumps(plan))
    unsigned["source_evidence"].pop("attestation", None)
    canonical = json.dumps({"user_id": user_id, "plan": unsigned},
                           sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(SECRET_KEY.encode(), canonical, hashlib.sha256).hexdigest()


def _attest_plan(plan: dict[str, Any], user_id: int) -> dict[str, Any]:
    plan["source_evidence"]["issued_at"] = datetime.now(timezone.utc).isoformat()
    plan["source_evidence"]["attestation"] = _attestation_digest(plan, user_id)
    return plan


def _verify_attestation(plan: dict[str, Any], user_id: int) -> None:
    evidence = plan.get("source_evidence") or {}
    issued = evidence.get("issued_at")
    signature = evidence.get("attestation")
    if not isinstance(issued, str) or not isinstance(signature, str):
        raise ValueError("manual_trade_attestation_missing")
    try:
        issued_at = _as_utc(datetime.fromisoformat(issued))
    except ValueError as exc:
        raise ValueError("manual_trade_attestation_invalid") from exc
    age = datetime.now(timezone.utc) - issued_at
    if age < timedelta(0) or age > ATTESTATION_LIFETIME:
        raise ValueError("manual_trade_attestation_expired")
    if not hmac.compare_digest(signature, _attestation_digest(plan, user_id)):
        raise ValueError("manual_trade_attestation_invalid")


def derive_suggested_plan(
    *, asset: str, quote_currency: str, direction: str, max_loss_quote: Any,
    candles: list[dict[str, Any]], market_id: int | None,
    now: datetime | None = None, context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate one limited-risk scenario; no broker order can consume it."""
    symbol = str(asset or "").upper()
    quote = str(quote_currency or "").upper()
    catalog = DEFAULT_ASSET_CATALOG.get(symbol) or {}
    asset_class = catalog.get("asset_class")
    if asset_class not in {"crypto", "stock"}:
        raise ValueError("manual_trade_asset_not_in_catalog")
    if asset_class == "stock" and quote != str(catalog.get("quote_currency") or "").upper():
        raise ValueError("manual_trade_quote_not_in_catalog")
    if asset_class == "crypto" and (quote not in {"EUR", "USDT"} or type(market_id) is not int or market_id <= 0):
        raise ValueError("manual_trade_exact_market_unavailable")
    if direction not in {"long", "short"}:
        raise ValueError("manual_trade_direction_required")
    budget = _positive_decimal(max_loss_quote, "max_loss_quote")
    if context is not None:
        factor = Decimal(str(context.get("risk_factor")))
        if factor not in {Decimal("1"), REDUCED_RISK_FACTOR}:
            raise ValueError("manual_trade_risk_factor_invalid")
        effective_budget = budget * factor
    else:
        effective_budget = budget
    if len(candles) < 15:
        raise ValueError("manual_trade_candles_insufficient")
    ordered = sorted(candles, key=lambda row: _as_utc(row["source_observed_at"]))
    if len({row["source_observed_at"].date() for row in ordered}) != len(ordered):
        raise ValueError("manual_trade_candles_duplicate_day")
    ordered = ordered[-15:]
    max_gap_days = 1 if asset_class == "crypto" else 5
    if any((later["source_observed_at"].date() - earlier["source_observed_at"].date()).days > max_gap_days
           for earlier, later in zip(ordered, ordered[1:])):
        raise ValueError("manual_trade_candles_gap")
    now = now or datetime.now(timezone.utc)
    latest_at = _as_utc(ordered[-1]["source_observed_at"])
    if latest_at > now or now - latest_at > timedelta(days=3 if asset_class == "crypto" else 7):
        raise ValueError("manual_trade_candles_stale")
    values = []
    candle_fingerprint_rows = []
    for row in ordered:
        open_price = _positive_decimal(row["open"], "candle_open")
        high = _positive_decimal(row["high"], "candle_high")
        low = _positive_decimal(row["low"], "candle_low")
        close = _positive_decimal(row["price"], "candle_close")
        if not low <= open_price <= high or not low <= close <= high:
            raise ValueError("manual_trade_candle_geometry_invalid")
        values.append((high, low, close))
        candle_fingerprint_rows.append({
            "id": int(row["id"]),
            "observed_at": _as_utc(row["source_observed_at"]).isoformat(),
            "open": str(open_price), "high": str(high), "low": str(low), "close": str(close),
        })
    true_ranges = [
        max(high - low, abs(high - values[index - 1][2]), abs(low - values[index - 1][2]))
        for index, (high, low, _) in enumerate(values) if index > 0
    ]
    atr = sum(true_ranges) / Decimal(14)
    entry = values[-1][2]
    price_step = Decimal("0.01") if asset_class == "stock" else Decimal("0.00000001")
    unit_step = Decimal("0.0001") if asset_class == "stock" else Decimal("0.00000001")
    risk_unit = (atr * Decimal("1.5")).quantize(price_step)
    if risk_unit <= 0 or (direction == "long" and risk_unit >= entry):
        raise ValueError("manual_trade_volatility_unusable")
    quantity = (effective_budget / risk_unit).quantize(unit_step, rounding=ROUND_DOWN)
    if quantity <= 0:
        raise ValueError("manual_trade_risk_budget_too_small")
    sign = Decimal(1) if direction == "long" else Decimal(-1)
    stop = entry - sign * risk_unit
    targets = [entry + sign * risk_unit * multiplier for multiplier in (Decimal(1), Decimal(2))]
    plan = validate_manual_trade_plan({
        "asset": symbol, "quote_currency": quote, "direction": direction,
        "entry_type": "limit", "entry_price": str(entry), "quantity": str(quantity),
        "stop_loss": str(stop), "targets": [str(value) for value in targets],
    })
    plan["level_source"] = "market_derived"
    plan["source_evidence"] = {
        "method_version": METHOD_VERSION, "market_id": market_id,
        "candle_ids": [int(row["id"]) for row in ordered],
        "candles_sha256": hashlib.sha256(json.dumps({
            "asset": symbol, "quote_currency": quote,
            "provider": str(catalog.get("primary_provider") or "").lower(),
            "provider_symbol": (f"{symbol}{quote}" if asset_class == "crypto"
                                else str(catalog.get("provider_symbol") or "").upper()),
            "venue": str(catalog.get("exchange") or "").upper(),
            "candles": candle_fingerprint_rows,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "source_observed_at": latest_at.isoformat(),
        "max_loss_quote": str(budget), "atr_quote": str(atr),
        "provider": str(catalog.get("primary_provider") or "").lower(),
        "provider_symbol": (f"{symbol}{quote}" if asset_class == "crypto"
                            else str(catalog.get("provider_symbol") or "").upper()),
        **({"owner_context": context} if context is not None else {}),
    }
    return plan


async def _source_candles(session: Any, *, asset: str, quote_currency: str) -> tuple[int | None, list[dict[str, Any]]]:
    symbol = str(asset or "").upper()
    quote = str(quote_currency or "").upper()
    catalog = DEFAULT_ASSET_CATALOG.get(symbol) or {}
    if catalog.get("asset_class") == "crypto":
        market = await session.execute(text(
            "SELECT id FROM trading_markets WHERE asset_symbol=:asset AND quote_currency=:quote "
            "AND venue=:venue AND is_active=TRUE LIMIT 1"
        ), {"asset": symbol, "quote": quote, "venue": str(catalog.get("exchange") or "").upper()})
        market_id = market.scalar_one_or_none()
        if market_id is None:
            raise ValueError("manual_trade_exact_market_unavailable")
        rows = await session.execute(text(
            "SELECT id,open,high,low,price,source_observed_at FROM market_data "
            "WHERE market_id=:market_id AND symbol=:asset AND quote_currency=:quote "
            "AND is_final_candle=TRUE AND source_observed_at < CURRENT_DATE "
            "AND price_provider=:provider "
            "AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND price IS NOT NULL "
            "ORDER BY source_observed_at DESC,id DESC LIMIT 15"
        ), {"market_id": market_id, "asset": symbol, "quote": quote,
            "provider": str(catalog.get("primary_provider") or "").lower()})
    elif catalog.get("asset_class") == "stock" and quote == str(catalog.get("quote_currency") or "").upper():
        from backend.schemas.market_provider_schema import AssetRecord
        from backend.services.market_data_provider_registry import MarketDataProviderRegistry

        market_id = None
        asset_record = AssetRecord(**catalog)
        provider = MarketDataProviderRegistry().resolve_for_asset(asset_record)
        candles = await provider.fetch_candles(asset_record, "1day", limit=40)
        exchange_zone = ZoneInfo(asset_record.timezone)
        today = datetime.now(exchange_zone).date()
        completed = sorted((candle for candle in candles
                            if candle.is_final
                            and candle.symbol.upper() == symbol
                            and candle.provider.lower() == provider.provider_name
                            and candle.provider_symbol.upper() == str(asset_record.provider_symbol or symbol).upper()
                            and str((candle.raw_payload.get("_source_meta") or {}).get("symbol") or "").upper() == str(asset_record.provider_symbol or symbol).upper()
                            and str((candle.raw_payload.get("_source_meta") or {}).get("currency") or "").upper() == quote
                            and str((candle.raw_payload.get("_source_meta") or {}).get("exchange") or "").upper() == str(asset_record.exchange or "").upper()
                            and candle.period_start.astimezone(exchange_zone).date() < today),
                           key=lambda candle: candle.period_start)
        rows = [{"id": int(candle.period_start.astimezone(exchange_zone).strftime("%Y%m%d")),
                 "open": candle.open, "high": candle.high, "low": candle.low, "price": candle.close,
                 "source_observed_at": candle.period_start}
                for candle in completed[-15:]]
    else:
        raise ValueError("manual_trade_asset_or_quote_unavailable")
    return (int(market_id) if market_id is not None else None,
            rows if isinstance(rows, list) else [dict(row) for row in reversed(rows.mappings().all())])


async def suggest_manual_trade_plan(session: Any, *, asset: str, quote_currency: str,
                                    direction: str, max_loss_quote: Any,
                                    user_id: int | None = None) -> dict[str, Any]:
    market_id, candles = await _source_candles(session, asset=asset, quote_currency=quote_currency)
    context = (await _owner_trade_context(session, user_id=user_id, asset=asset.upper(),
                                          quote_currency=quote_currency.upper(), market_id=market_id)
               if user_id is not None else None)
    if (context is not None and context.get("recommendation") == "wait"
            and context.get("reason") != "manual_trade_setup_outside_conditions"):
        # A measured score mismatch still has verified levels and can show a
        # non-executable card with wait advice. Missing or conflicting source
        # evidence cannot support a confirmable proposal.
        raise ManualTradeWait(str(context.get("reason") or "manual_trade_context_unavailable"))
    plan = derive_suggested_plan(asset=asset, quote_currency=quote_currency,
                                 direction=direction, max_loss_quote=max_loss_quote,
                                 candles=candles, market_id=market_id, context=context)
    return _attest_plan(plan, user_id) if user_id is not None else plan


async def verify_suggested_manual_trade_plan(session: Any, plan: dict[str, Any],
                                             *, user_id: int | None = None) -> None:
    evidence = plan.get("source_evidence") or {}
    if evidence.get("method_version") != METHOD_VERSION:
        raise ValueError("manual_trade_source_version_invalid")
    if user_id is not None:
        _verify_attestation(plan, user_id)
        context = await _owner_trade_context(
            session, user_id=user_id, asset=str(plan.get("asset") or "").upper(),
            quote_currency=str(plan.get("quote_currency") or "").upper(),
            market_id=evidence.get("market_id"),
        )
        if (context.get("recommendation") == "wait"
                and context.get("reason") != "manual_trade_setup_outside_conditions"):
            raise ManualTradeWait(str(context.get("reason") or "manual_trade_context_unavailable"))
        if context != evidence.get("owner_context"):
            raise ValueError("manual_trade_owner_context_changed")
        # A signed provider response remains valid for a short review window.
        # Confirmation and storage never hold a DB transaction across HTTP.
        if plan.get("asset_class") == "stock":
            return
    market_id, candles = await _source_candles(
        session, asset=plan.get("asset"), quote_currency=plan.get("quote_currency"),
    )
    context = (await _owner_trade_context(session, user_id=user_id,
                                          asset=str(plan.get("asset") or "").upper(),
                                          quote_currency=str(plan.get("quote_currency") or "").upper(),
                                          market_id=market_id)
               if user_id is not None else None)
    expected = derive_suggested_plan(
        asset=plan.get("asset"), quote_currency=plan.get("quote_currency"),
        direction=plan.get("direction"), max_loss_quote=evidence.get("max_loss_quote"),
        candles=candles, market_id=market_id, context=context,
    )
    checked_plan = dict(plan)
    checked_plan["source_evidence"] = {key: value for key, value in evidence.items()
                                       if key not in {"issued_at", "attestation"}}
    if expected != checked_plan:
        raise ValueError("manual_trade_source_changed")
