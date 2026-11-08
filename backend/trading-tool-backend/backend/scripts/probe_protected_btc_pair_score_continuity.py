"""Protected owner-scoped BTC pair score outage/recovery probe.

This module is not a public entry point. The protected QA runner must verify
release identity, fixture auth, namespace and action authorization first.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts.qa_trader_gate_invariants import check_pair_score_isolation


def _markets() -> dict[str, dict]:
    from backend.utils.scoring_utils import score_source_is_fresh

    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT id, quote_currency FROM trading_markets
                              WHERE asset_symbol='BTC' AND quote_currency IN ('EUR','USDT')
                                AND venue='BINANCE' AND is_active=TRUE""")
            rows = cursor.fetchall()
            markets = {}
            for market_id, quote in rows:
                cursor.execute("""SELECT change_24h, source_observed_at
                                  FROM market_data
                                  WHERE market_id=%s AND quote_currency IS NOT NULL
                                    AND source_observed_at IS NOT NULL
                                  ORDER BY source_observed_at DESC, timestamp DESC LIMIT 1""",
                               (market_id,))
                source = cursor.fetchone()
                if (not source or source[0] is None
                        or not score_source_is_fresh("market", "change_24h", source[1], symbol="BTC")):
                    raise RuntimeError("btc_pair_source_unavailable")
                markets[f"BTC/{quote}"] = {
                    "market_id": int(market_id), "change_24h": source[0],
                    "source_at": source[1],
                }
        if (
            len(rows) != 2
            or set(markets) != {"BTC/EUR", "BTC/USDT"}
            or len({item["market_id"] for item in markets.values()}) != 2
        ):
            raise RuntimeError("btc_pair_markets_unavailable")
        return markets
    finally:
        connection.close()


def _seed_pair_readings(user_id: int, markets: dict[str, dict]) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO user_indicator_configs
                (user_id,indicator,category,symbol,asset_class,priority,enabled,created_at,updated_at)
                VALUES (%s,'dxy','macro','BTC','crypto',1,TRUE,%s,%s)""",
                (user_id, now, now))
            for days_ago, dxy in ((4, 101.5), (3, 101.7), (2, 101.9), (1, 102.1), (0, 102.2)):
                observed = now - timedelta(days=days_ago)
                cursor.execute("""INSERT INTO macro_data
                    (user_id,symbol,name,value,timestamp,source_observed_at)
                    VALUES (%s,'BTC','dxy',%s,%s,%s)""",
                    (user_id, dxy, observed, observed))
            for pair, source in markets.items():
                market_id = source["market_id"]
                for category, indicator in (("market", "change_24h"), ("technical", "rsi")):
                    cursor.execute("""INSERT INTO user_indicator_configs
                        (user_id,indicator,category,symbol,asset_class,priority,enabled,
                         created_at,updated_at,market_id)
                        VALUES (%s,%s,%s,'BTC','crypto',1,TRUE,%s,%s,%s)""",
                        (user_id, indicator, category, now, now, market_id))
                cursor.execute("""INSERT INTO market_data_indicators
                    (user_id,symbol,name,value,timestamp,source_observed_at,market_id)
                    VALUES (%s,'BTC','change_24h',%s,%s,%s,%s)""",
                    (user_id, source["change_24h"], source["source_at"],
                     source["source_at"], market_id))
                cursor.execute("""INSERT INTO technical_indicators
                    (user_id,symbol,indicator,value,timestamp,source_observed_at,market_id)
                    VALUES (%s,'BTC','rsi',%s,%s,%s,%s)""",
                    (user_id, 25 if pair == "BTC/EUR" else 75, now, now, market_id))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _set_eur_source_time(user_id: int, market_id: int, source_at: datetime,
                         *, stale: bool) -> None:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE market_data_indicators
                SET source_observed_at=CASE WHEN %s THEN NOW()-INTERVAL '30 days' ELSE %s END,
                    timestamp=CASE WHEN %s THEN NOW()-INTERVAL '30 days' ELSE %s END
                WHERE user_id=%s AND symbol='BTC' AND market_id=%s AND name='change_24h'""",
                (stale, source_at, stale, source_at, user_id, market_id))
            if cursor.rowcount != 1:
                raise RuntimeError("btc_pair_fixture_source_missing")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def _assessment(user_id: int, market_id: int) -> dict:
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.setup_market_match_service import SetupMarketMatchService

    try:
        async with async_session_factory() as session:
            return await SetupMarketMatchService(session).for_asset(
                user_id, "BTC", setups=[], market_id=market_id,
            )
    finally:
        await engine.dispose()


def _snapshot(user_id: int, markets: dict[str, dict]) -> dict:
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_market

    connection = fixture._connection()
    try:
        pairs = {}
        for pair, source in markets.items():
            market_id = source["market_id"]
            build_daily_scores_for_market(user_id, market_id)
            assessment = asyncio.run(_assessment(user_id, market_id))
            with connection.cursor() as cursor:
                cursor.execute("""SELECT source_observed_at FROM market_data_indicators
                                  WHERE user_id=%s AND symbol='BTC' AND market_id=%s
                                    AND name='change_24h'
                                  ORDER BY source_observed_at DESC LIMIT 1""",
                               (user_id, market_id))
                observed = cursor.fetchone()
                cursor.execute("""SELECT category, indicator FROM user_indicator_configs
                                  WHERE user_id=%s AND symbol='BTC' AND market_id=%s
                                  ORDER BY category, indicator""", (user_id, market_id))
                config = tuple(cursor.fetchall())
            components = assessment.get("component_source_status") or {}
            market_reason = components.get("market_score")
            verified = assessment.get("source_status") == "available" and assessment.get("benchmark_score") is not None
            pairs[pair] = {
                "owner_id": user_id, "market_id": market_id,
                "indicator_config": config,
                "source_at": (
                    (observed[0].replace(tzinfo=timezone.utc) if observed[0].tzinfo is None
                     else observed[0].astimezone(timezone.utc)).isoformat()
                    if observed else None
                ),
                "score": assessment.get("benchmark_score") if verified else None,
                "source_status": "fresh" if verified else market_reason,
                "source_reason": market_reason,
            }
        return {"pairs": pairs}
    finally:
        connection.close()


def run(namespace: str) -> dict:
    if os.getenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE") != "1":
        raise RuntimeError("trader_pair_fixture_not_authorized")
    if not fixture.NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("trader_pair_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    markets = _markets()  # No fixture write until both exact markets exist.
    user_id = bot_id = None
    passed = False
    try:
        user_id, bot_id, _ = fixture._seed(namespace, int(bound))
        _seed_pair_readings(user_id, markets)
        initial = _snapshot(user_id, markets)
        _set_eur_source_time(user_id, markets["BTC/EUR"]["market_id"],
                             markets["BTC/EUR"]["source_at"], stale=True)
        outage = _snapshot(user_id, markets)
        _set_eur_source_time(user_id, markets["BTC/EUR"]["market_id"],
                             markets["BTC/EUR"]["source_at"], stale=False)
        recovered = _snapshot(user_id, markets)
        result = check_pair_score_isolation(
            owner_id=user_id, initial=initial, outage=outage, recovered=recovered,
        )
        if result["result"] != "PASS":
            return result
        passed = True
        return {**result, "pairs": 2, "phases": 3,
                "source_outage": "owner_scoped", "live_calls": 0}
    finally:
        if user_id is not None and bot_id is not None:
            if passed:
                fixture._cleanup(namespace, user_id, bot_id)
            else:
                fixture._quarantine(namespace, user_id, bot_id)
