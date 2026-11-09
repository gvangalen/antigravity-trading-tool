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


def _transport_checks(user_id: int, snapshot: dict) -> dict[str, bool]:
    """Compare normal owner-scoped Analysis GET and FINN chat reads with frozen scores."""
    from backend.scripts.qa_protected_readback import read_json
    from backend.scripts.probe_protected_account_answer import _read_tool_results
    from backend.scripts.probe_protected_closed_paper_review import _chat_turn

    checks = {"analysis": True, "finn": True}
    for pair, expected in snapshot["pairs"].items():
        quote = pair.split("/", 1)[1]
        try:
            analysis = read_json(
                owner_id=user_id,
                path=f"/api/workspace/exact-market?symbol=BTC&quote_currency={quote}",
            )
            checks["analysis"] &= (
                analysis.get("market_id") == expected["market_id"]
                and analysis.get("pair") == pair
                and (analysis.get("combined") or {}).get("score") == expected["score"]
            )
        except Exception:
            checks["analysis"] = False
        try:
            turn = asyncio.run(_chat_turn(
                user_id,
                f"Lees alleen mijn actuele Score 2.0 voor {pair} uit opgeslagen brondata. "
                "Geef de benchmarkscore en bronstatus; wijzig niets.",
            ))
            if (turn.status != "completed" or turn.response is None
                    or turn.response.proposal_id
                    or turn.response.confirmation_required
                    or turn.policy and turn.policy.execute_allowed):
                checks["finn"] = False
                continue
            rows = asyncio.run(_read_tool_results(
                run_id=turn.run_id, conversation_id=turn.conversation_id, user_id=user_id,
            ))
            matches = [row["data"] for row in rows if isinstance(row, dict)
                       and row.get("scope") == "read_asset_scores"
                       and row.get("status") == "completed"
                       and isinstance(row.get("data"), dict)
                       and row["data"].get("market_id") == expected["market_id"]
                       and row["data"].get("pair") == pair]
            checks["finn"] &= len(matches) == 1 and matches[0].get("benchmark_score") == expected["score"]
        except Exception:
            checks["finn"] = False
    return checks


async def _stale_date_display(user_id: int, source_at: str) -> dict[str, bool]:
    """Exercise the deployed short UTC source-date formatter across offset zones."""
    from backend.scripts.qa_protected_browser import observe_page
    from backend.utils.auth_utils import create_access_token

    token = create_access_token({"sub": str(user_id), "role": "user"})
    checks = {}
    try:
        for zone in ("Europe/Amsterdam", "America/New_York", "Asia/Tokyo"):
            async def inspect(page):
                expected = await page.evaluate(
                    "source => new Intl.DateTimeFormat('nl-NL', "
                    "{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(source))",
                    source_at,
                )
                try:
                    await page.get_by_text(expected, exact=False).first.wait_for(timeout=15000)
                    return True
                except Exception:
                    return False
            try:
                checks[zone.split("/")[-1].lower()] = await observe_page(
                    base_url="https://tradamind.com", path="/asset?symbol=BTC&quote=EUR",
                    token=token, inspect=inspect, timezone_id=zone,
                    bypass_fixture_onboarding=True,
                ) is True
            except Exception:
                checks[zone.split("/")[-1].lower()] = False
        return checks
    finally:
        token = None


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
    selected_at = ((datetime.now(timezone.utc) - timedelta(days=30)).replace(
        hour=0, minute=30, second=0, microsecond=0, tzinfo=None,
    ) if stale else source_at)
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE market_data_indicators
                SET source_observed_at=%s, timestamp=%s
                WHERE user_id=%s AND symbol='BTC' AND market_id=%s AND name='change_24h'""",
                (selected_at, selected_at, user_id, market_id))
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
    from backend.utils.scoring_utils import score_source_is_fresh

    connection = fixture._connection()
    try:
        pairs = {}
        for pair, source in markets.items():
            market_id = source["market_id"]
            built = build_daily_scores_for_market(user_id, market_id)
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
            stale_reading_proven = bool(
                observed and observed[0] is not None
                and not score_source_is_fresh(
                    "market", "change_24h", observed[0], symbol="BTC",
                )
                and (built.get("scores") or {}).get("market") is None
            )
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
                "fixture_source_diagnosis": (
                    "stale_source" if stale_reading_proven else "fresh" if verified
                    else "unknown"
                ),
                "stale_reading_proven": stale_reading_proven,
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
        initial_transport = _transport_checks(user_id, initial)
        _set_eur_source_time(user_id, markets["BTC/EUR"]["market_id"],
                             markets["BTC/EUR"]["source_at"], stale=True)
        outage = _snapshot(user_id, markets)
        outage_transport = _transport_checks(user_id, outage)
        try:
            stale_browser = asyncio.run(_stale_date_display(
                user_id, outage["pairs"]["BTC/EUR"]["source_at"],
            ))
        except Exception:
            stale_browser = {}
        _set_eur_source_time(user_id, markets["BTC/EUR"]["market_id"],
                             markets["BTC/EUR"]["source_at"], stale=False)
        recovered = _snapshot(user_id, markets)
        recovered_transport = _transport_checks(user_id, recovered)
        result = check_pair_score_isolation(
            owner_id=user_id, initial=initial, outage=outage, recovered=recovered,
        )
        transport = (initial_transport, outage_transport, recovered_transport)
        transport_failures = [
            f"{name}_transport_{surface}"
            for name, checks in zip(("initial", "outage", "recovered"), transport)
            for surface, passed_check in checks.items() if not passed_check
        ]
        if len(stale_browser) != 3 or not all(stale_browser.values()):
            transport_failures.append("outage_stale_date_browser")
        if transport_failures:
            return {"result": "FAIL", "failed_checks": sorted(set(
                result["failed_checks"] + transport_failures)),
                "pairs": 2, "phases": 3, "analysis_transport_checked": True,
                "finn_transport_checked": True, "stale_date_browser_checked": True,
                "gate_status": "FAIL", "live_calls": 0}
        if result["result"] != "PASS":
            return {**result, "gate_status": "FAIL",
                    "analysis_transport_checked": True,
                    "finn_transport_checked": True,
                    "stale_date_browser_checked": True}
        passed = True
        return {**result, "pairs": 2, "phases": 3,
                "source_outage": "owner_scoped", "live_calls": 0,
                "analysis_transport_checked": True,
                "finn_transport_checked": True,
                "stale_date_browser_checked": True,
                "gate_status": "PASS"}
    finally:
        if user_id is not None and bot_id is not None:
            if passed:
                fixture._cleanup(namespace, user_id, bot_id)
            else:
                fixture._quarantine(namespace, user_id, bot_id)
