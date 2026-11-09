"""Protected owner-scoped BTC pair score outage/recovery probe.

This module is not a public entry point. The protected QA runner must verify
release identity, fixture auth, namespace and action authorization first.
"""

from __future__ import annotations

import asyncio
import math
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts.qa_trader_gate_invariants import check_pair_score_isolation


_ASSESSMENT_ERROR_KINDS = frozenset({
    "RuntimeError", "TypeError", "ValueError", "AttributeError", "KeyError",
    "OperationalError", "DataError", "IntegrityError", "ProgrammingError",
    "StatementError",
})
_ASSESSMENT_ORIGINS = {
    ("setup_market_match_service.py", "for_asset"): "match_asset",
    ("setup_market_match_service.py", "_source_is_fresh"): "match_source",
    ("setup_market_match_service.py", "_benchmark_weights"): "match_weights",
    ("pair_benchmark_service.py", "benchmark_weights"): "pair_weights",
    ("scoring_utils.py", "score_snapshot_diagnosis"): "score_diagnosis",
}
_SAFE_FINN_ERROR_CODES = frozenset({
    "orchestrator_failed", "selector_phase_timeout", "lifecycle_deadline_exceeded",
    "responses_provider_quota_unavailable", "runtime_contract_terminal_projection_missing",
    "tool_execution_failed", "run_canceled",
    "responses_evidence_not_verified", "insufficient_evidence", "source_unavailable",
    "responses_tool_execution_failed", "responses_provider_timeout",
    "responses_provider_error", "responses_lifecycle_budget_exhausted",
    "responses_tool_round_limit", "responses_incomplete", "responses_empty_answer",
    "responses_selection_missing", "responses_internal_preamble_without_answer",
    "tool_relevance_unverified", "tool_not_relevant_to_request",
    "market_pair_ambiguous", "market_pair_not_supported", "score_missing",
    "turn_contract_mismatch", "price_relation_conflicts_with_source",
})
_SAFE_FINN_STATUSES = frozenset({
    "created", "queued", "collecting", "planned", "reasoning", "verifying",
    "clarification_required", "unavailable", "downgraded", "rejected",
    "blocked", "completed", "failed", "canceled",
})
_SAFE_PROVIDER_EXCEPTIONS = frozenset({
    "BadRequestError", "AuthenticationError", "PermissionDeniedError",
    "RateLimitError", "InternalServerError", "APIStatusError", "APIConnectionError",
    "APITimeoutError", "ConnectError", "ReadError",
    "RuntimeError",
})


@contextmanager
def _provider_failure_probe():
    """Observe only a fixed SDK error class/status, never request or response data."""
    from openai.resources.responses import AsyncResponses

    original = AsyncResponses.create
    observations: list[dict[str, object]] = []
    calls = 0

    async def observed_create(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        try:
            return await original(self, *args, **kwargs)
        except Exception as error:
            status = getattr(error, "status_code", None)
            status_class = (
                "429" if status == 429 else
                "4xx" if isinstance(status, int) and 400 <= status < 500 else
                "5xx" if isinstance(status, int) and 500 <= status < 600 else
                "none" if status is None else "other"
            )
            kind = type(error).__name__
            observations.append({
                "provider_call": calls if calls <= 3 else "4_plus",
                "status_class": status_class,
                "exception_kind": kind if kind in _SAFE_PROVIDER_EXCEPTIONS else "other",
            })
            raise

    with patch.object(AsyncResponses, "create", observed_create):
        yield observations


def _assessment_error_code(error: Exception) -> str:
    """Classify only a fixed exception type and static source function."""
    kind = type(error).__name__
    if kind not in _ASSESSMENT_ERROR_KINDS:
        kind = "Other"
    origin = "other"
    frame = error.__traceback__
    while frame is not None:
        code = frame.tb_frame.f_code
        name = code.co_filename.rsplit("/", 1)[-1]
        origin = _ASSESSMENT_ORIGINS.get((name, code.co_name), origin)
        frame = frame.tb_next
    return f"{kind.lower()}_{origin}"


def _finn_terminal_diagnostic(turn) -> dict[str, str]:
    """Export only enum-like terminal fields, never answer or error text."""
    trace = turn.runtime_trace if isinstance(getattr(turn, "runtime_trace", None), dict) else {}
    reasoning = trace.get("reasoning") if isinstance(trace.get("reasoning"), dict) else {}
    orchestrator = trace.get("orchestrator") if isinstance(trace.get("orchestrator"), dict) else {}
    status = getattr(turn, "status", None)
    error_code = getattr(turn, "error_code", None)
    return {
        "status": status if status in _SAFE_FINN_STATUSES else "other",
        "error_code": (error_code if error_code in _SAFE_FINN_ERROR_CODES
                       else "none" if error_code is None else "other"),
        "reasoning_status": (reasoning.get("status") if reasoning.get("status") in {
            "completed", "failed", "unavailable", "partial", "pending",
        } else "other"),
        "orchestrator_outcome": (orchestrator.get("outcome") if orchestrator.get("outcome") in {
            "completed", "failed", "unavailable", "clarification_required",
        } else "other"),
    }


def _business_snapshot(user_id: int) -> dict:
    from backend.scripts.probe_protected_account_answer import _business_state

    return _business_state(user_id, diagnostic=True)


async def _score_tool_seen(*, user_id: int, run_id: str, conversation_id: str) -> bool | str:
    """Whether an owner-bound durable trace recorded a score tool, including progress."""
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import (
        FinnV2RuntimeContractRepository,
    )

    try:
        async with async_session_factory() as session:
            contract = await FinnV2RuntimeContractRepository(session).get_for_run(run_id=run_id)
            if (contract is None or contract.user_id != user_id
                    or contract.conversation_id != conversation_id):
                return "unknown"
            state = contract.state_json or {}
            checkpoints = [state[name] for name in ("responses_exchange", "responses_progress")
                           if state.get(name) is not None]
            if any(not isinstance(checkpoint, dict)
                   or checkpoint.get("run_id") != run_id
                   or checkpoint.get("conversation_id") != conversation_id
                   or not isinstance(checkpoint.get("tool_trace"), list)
                   for checkpoint in checkpoints):
                return "unknown"
            return any(
                isinstance(call, dict) and isinstance(call.get("result"), dict)
                and any(isinstance(row, dict) and row.get("scope") == "read_asset_scores"
                        for row in (call["result"].get("results") or []))
                for checkpoint in checkpoints for call in checkpoint["tool_trace"]
            )
    except Exception:
        return "unknown"


async def _finn_pair_read(user_id: int, pair: str):
    """Keep the FINN turn and its evidence on one loop, then release the pool."""
    from backend.infrastructure.database import engine
    from backend.scripts.probe_protected_account_answer import _read_tool_results
    from backend.scripts.probe_protected_closed_paper_review import _chat_turn

    try:
        with _provider_failure_probe() as provider_failures:
            turn = await _chat_turn(
                user_id,
                f"Lees alleen mijn actuele Score 2.0 voor {pair} uit opgeslagen brondata. "
                "Geef de benchmarkscore en bronstatus; wijzig niets.",
            )
        if turn.status != "completed":
            status = turn.status if turn.status in _SAFE_FINN_STATUSES else "other"
            diagnostic = _finn_terminal_diagnostic(turn)
            if diagnostic["error_code"] == "responses_provider_error":
                diagnostic["provider_failure"] = (
                    provider_failures[-1] if provider_failures else {"provider_call": 0,
                        "status_class": "unobserved", "exception_kind": "unobserved"}
                )
                diagnostic["score_tool_seen"] = await _score_tool_seen(
                    run_id=turn.run_id, conversation_id=turn.conversation_id, user_id=user_id,
                )
            return None, f"turn_{status}", diagnostic
        if turn.response is None:
            return None, "response_missing", _finn_terminal_diagnostic(turn)
        if (turn.response.proposal_id or turn.response.confirmation_required
                or turn.policy and turn.policy.execute_allowed):
            return None, "action_boundary", _finn_terminal_diagnostic(turn)
        rows = await _read_tool_results(
            run_id=turn.run_id, conversation_id=turn.conversation_id, user_id=user_id,
        )
        return rows, "ok", None
    finally:
        await engine.dispose()


async def _read_finn_pairs(user_id: int, pairs: list[str]) -> dict:
    """Read both exact pairs on one loop for the shared async provider client."""
    results = {}
    for pair in pairs:
        try:
            results[pair] = await _finn_pair_read(user_id, pair)
        except Exception:
            results[pair] = (None, "read_error", None)
    return results


class _LoopRunner:
    """Run every protected FINN/browser read on one Python 3.10-compatible loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def run(self, coroutine):
        return self.loop.run_until_complete(coroutine)


@contextmanager
def _shared_loop_runner():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        yield _LoopRunner(loop)
    finally:
        try:
            if not loop.is_closed():
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                if hasattr(loop, "shutdown_default_executor"):
                    loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def _transport_checks(user_id: int, snapshot: dict,
                      runner: _LoopRunner | None = None) -> dict[str, bool]:
    """Compare normal owner-scoped Analysis GET and FINN chat reads with frozen scores."""
    from backend.scripts.qa_protected_readback import read_json

    checks = {"analysis": True, "finn": True, "finn_codes": {}, "finn_runtime_codes": {}}
    pairs = list(snapshot["pairs"])
    finn_results = (runner.run(_read_finn_pairs(user_id, pairs)) if runner is not None
                    else asyncio.run(_read_finn_pairs(user_id, pairs)))
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
            rows, phase, runtime_code = finn_results[pair]
            if rows is None:
                checks["finn"] = False
                checks["finn_codes"][pair] = phase
                if runtime_code:
                    checks["finn_runtime_codes"][pair] = runtime_code
                continue
            scoped = [row for row in rows if isinstance(row, dict)
                      and row.get("scope") == "read_asset_scores"]
            if not scoped:
                phase = "scope_missing"
            elif len(scoped) != 1:
                phase = "scope_ambiguous"
            elif scoped[0].get("status") != "completed" or not isinstance(scoped[0].get("data"), dict):
                phase = "scope_unverified"
            elif scoped[0]["data"].get("pair") != pair:
                phase = "pair_mismatch"
            elif scoped[0]["data"].get("market_id") != expected["market_id"]:
                phase = "market_mismatch"
            elif scoped[0]["data"].get("benchmark_score") != expected["score"]:
                phase = "score_mismatch"
            checks["finn"] &= phase == "ok"
            checks["finn_codes"][pair] = phase
        except Exception:
            checks["finn"] = False
            checks["finn_codes"][pair] = "read_error"
    return checks


async def _outage_indicator_visible(page, *, old_source_time: str,
                                    current_quote_time: str,
                                    timeout_ms: int = 15000) -> str:
    """Require the old measurement date in the exact visible BTC/EUR row."""
    try:
        market = page.get_by_role("heading", name="Markt", exact=True).locator(
            "xpath=ancestor::section[1]")
        if await market.count() != 1:
            return "market_section_missing"
        indicator = market.get_by_role("button").filter(has_text="Prijsverandering 24 uur")
        if await indicator.count() != 1:
            return "indicator_missing"
        for expected, missing in (
            ("Score wordt berekend", "pending_label_missing"),
            (f"Laatste indicatormeting: {old_source_time}", "old_indicator_moment_missing"),
            (f"Getoonde 24-uursverandering uit koersbron: {current_quote_time}",
             "current_quote_moment_missing"),
        ):
            try:
                await indicator.get_by_text(expected, exact=False).wait_for(timeout=timeout_ms)
            except Exception:
                return missing
        return "ok"
    except Exception:
        return "indicator_inspection_failed"


async def _stale_date_display(user_id: int, source_at: str, market_id: int,
                              source_facts: dict | None = None) -> dict[str, str]:
    """Check the current quote date and pending pair score during an outage."""
    from backend.scripts.qa_protected_browser import observe_page
    from backend.scripts.qa_protected_readback import read_json
    from backend.scripts.probe_protected_source_time_parity import _normalized_ref, _target_quote_visible
    from backend.utils.auth_utils import create_access_token
    from urllib.parse import urlsplit

    token = create_access_token({"sub": str(user_id), "role": "user"})
    checks = {}
    try:
        for zone in ("Europe/Amsterdam", "America/New_York", "Asia/Tokyo"):
            zone_code = zone.split("/")[-1].lower()
            observed_responses = []
            selection_state = {"code": "request_absent"}

            def selection_readback():
                selection_state["code"] = "owner_get_error"
                workspace = read_json(
                    owner_id=user_id,
                    path="/api/workspace/exact-market?symbol=BTC&quote_currency=EUR",
                )
                selection_state["code"] = "owner_get_invariant"
                stale_moment = ((workspace.get("score_source_observed_at") or {})
                                .get("market") or {}).get("change_24h")
                expected_stale = None
                try:
                    expected_stale = datetime.fromisoformat(str(source_at).replace("Z", "+00:00"))
                except ValueError:
                    pass
                if expected_stale is not None:
                    expected_stale = expected_stale.replace(
                        tzinfo=expected_stale.tzinfo or timezone.utc,
                    ).astimezone(timezone.utc)
                # A pending score may have no verified score-source projection.
                # The independent fixture snapshot and visible indicator row
                # still prove the old measurement instant exactly.
                same_saved_source = stale_moment is None
                if stale_moment is not None:
                    try:
                        selected_stale = datetime.fromisoformat(str(stale_moment).replace("Z", "+00:00"))
                        same_saved_source = (
                            selected_stale.replace(tzinfo=selected_stale.tzinfo or timezone.utc)
                            .astimezone(timezone.utc) == expected_stale
                        )
                    except ValueError:
                        same_saved_source = False
                row = [item for item in (workspace.get("categories") or {}).get("market", {}).get("rows", [])
                       if item.get("name") == "change_24h"]
                quote_ref = _normalized_ref((workspace.get("quote") or {}).get("source_ref"))
                if source_facts is not None:
                    reason = row[0].get("score_unavailable_reason") if len(row) == 1 else None
                    safe_reasons = {"score_pending", "stale_source", "missing_rule",
                                    "missing_source_reading", "insufficient_dated_history"}
                    source_facts[zone_code] = {
                        "reason": reason if isinstance(reason, str) and reason in safe_reasons else "other",
                        "old_indicator_moment_present": bool(
                            len(row) == 1 and row[0].get("indicator_source_observed_at")),
                        "current_quote_moment_present": bool(
                            len(row) == 1 and row[0].get("source_observed_at")),
                        "saved_score_source_present": stale_moment is not None,
                    }
                try:
                    row_old = datetime.fromisoformat(
                        str(row[0].get("indicator_source_observed_at")).replace("Z", "+00:00"))
                    row_current = datetime.fromisoformat(
                        str(row[0].get("source_observed_at")).replace("Z", "+00:00"))
                    row_old = row_old.replace(tzinfo=row_old.tzinfo or timezone.utc).astimezone(timezone.utc)
                    row_current = row_current.replace(tzinfo=row_current.tzinfo or timezone.utc).astimezone(timezone.utc)
                except (IndexError, ValueError):
                    row_old = row_current = None
                failed = [code for condition, code in (
                    (workspace.get("pair") != "BTC/EUR", "pair"),
                    (workspace.get("market_id") != market_id, "market"),
                    (quote_ref is None, "quote_ref_missing"),
                    (quote_ref is not None and quote_ref[0] != market_id, "quote_ref_market"),
                    (len(row) != 1, "indicator_row"),
                    (len(row) == 1 and row[0].get("score") is not None, "indicator_score"),
                    ((workspace.get("daily") or {}).get("market", {}).get("score") is not None, "daily_score"),
                    ((workspace.get("combined") or {}).get("score") is not None, "combined_score"),
                    (not same_saved_source, "saved_source"),
                    (row_old != expected_stale, "indicator_source"),
                    (row_current != (quote_ref[2] if quote_ref else None), "quote_source"),
                ) if condition]
                if failed:
                    selection_state["code"] = "owner_get_invariant_" + failed[0]
                    raise RuntimeError("trader_pair_browser_readback_invalid")
                selection_state["code"] = "owner_get_ok"
                return {"market_id": workspace["market_id"], "pair": "BTC/EUR",
                        "quote_currency": "EUR", "workspace": workspace}

            def observe_response(response):
                if urlsplit(response.url).path == "/api/assets/BTC/trading-markets/EUR/select":
                    observed_responses.append(response)
                    selection_state["code"] = "response_seen"

            async def inspect(page):
                try:
                    for _ in range(50):
                        if observed_responses:
                            break
                        await asyncio.sleep(0.1)
                    if not observed_responses:
                        return ("selection_response_absent" if selection_state["code"] == "owner_get_ok"
                                else selection_state["code"])
                    if observed_responses[-1].status != 200:
                        return "selection_response_error"
                    payload = await observed_responses[-1].json()
                    workspace = payload.get("workspace") or {}
                    quote_ref = _normalized_ref((workspace.get("quote") or {}).get("source_ref"))
                    if (workspace.get("pair") != "BTC/EUR" or workspace.get("market_id") != market_id
                            or quote_ref is None or quote_ref[0] != market_id):
                        return "api_source_unverified"
                    price = (workspace.get("quote") or {}).get("price")
                    if (isinstance(price, bool) or not isinstance(price, (int, float))
                            or not math.isfinite(price)):
                        return "api_price_unverified"
                    expected_price = await page.evaluate(
                        "price => new Intl.NumberFormat('nl-NL', "
                        "{style:'currency',currency:'EUR',maximumFractionDigits:price>=1000?0:2})"
                        ".format(price)",
                        price,
                    )
                    expected = await page.evaluate(
                        "source => new Intl.DateTimeFormat('nl-NL', "
                        "{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})"
                        ".format(new Date(source)) + ' UTC'",
                        quote_ref[2].isoformat(),
                    )
                    quote_phase = await _target_quote_visible(
                        page, surface="analysis", locale="nl-NL", expected=expected,
                        quote_currency="EUR", expected_price=expected_price,
                    )
                    if quote_phase != "ok":
                        return "quote_" + quote_phase
                    old_source_time = await page.evaluate(
                        "source => new Intl.DateTimeFormat('nl-NL', "
                        "{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})"
                        ".format(new Date(source)) + ' UTC'",
                        source_at,
                    )
                    return await _outage_indicator_visible(
                        page, old_source_time=old_source_time,
                        current_quote_time=expected,
                    )
                except Exception:
                    return "browser_inspection_failed"
            try:
                checks[zone_code] = await observe_page(
                    base_url="https://tradamind.com", path="/asset?symbol=BTC&quote=EUR",
                    token=token, inspect=inspect, timezone_id=zone,
                    bypass_fixture_onboarding=True,
                    observe_response=observe_response,
                    fixture_exact_selection=selection_readback,
                )
            except Exception:
                checks[zone_code] = "page_unavailable"
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
    step = "score_builder"
    try:
        pairs = {}
        for pair, source in markets.items():
            market_id = source["market_id"]
            step = "score_builder"
            built = build_daily_scores_for_market(user_id, market_id)
            step = "assessment"
            assessment = asyncio.run(_assessment(user_id, market_id))
            step = "source_read"
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
            step = "stale_eval"
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
            step = "projection"
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
    except Exception as error:
        if step == "assessment":
            raise RuntimeError(
                f"trader_pair_snapshot_assessment_{_assessment_error_code(error)}_failed"
            ) from None
        raise RuntimeError(f"trader_pair_snapshot_{step}_failed") from None
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
    user_id = bot_id = None
    passed = False
    stage = "markets"
    try:
        markets = _markets()  # No fixture write until both exact markets exist.
        stage = "seed"
        user_id, bot_id, _ = fixture._seed(namespace, int(bound))
        stage = "readings"
        _seed_pair_readings(user_id, markets)
        stage = "baseline"
        before_business = _business_snapshot(user_id)
        stage = "live_guard_import"
        from backend.scripts.probe_protected_paper_exit_reconciliation import _guard_live_exchange

        stage = "live_guard_entry"
        with _guard_live_exchange() as live_attempts:
            stage = "runner_entry"
            with _shared_loop_runner() as runner:
                stage = "initial_snapshot"
                initial = _snapshot(user_id, markets)
                stage = "initial_transport"
                initial_transport = _transport_checks(user_id, initial, runner=runner)
                stage = "outage_source"
                _set_eur_source_time(user_id, markets["BTC/EUR"]["market_id"],
                                     markets["BTC/EUR"]["source_at"], stale=True)
                stage = "outage_snapshot"
                outage = _snapshot(user_id, markets)
                stage = "outage_transport"
                outage_transport = _transport_checks(user_id, outage, runner=runner)
                stage = "browser"
                browser_source_facts = {}
                try:
                    stale_browser = runner.run(_stale_date_display(
                        user_id, outage["pairs"]["BTC/EUR"]["source_at"],
                        markets["BTC/EUR"]["market_id"],
                        source_facts=browser_source_facts,
                    ))
                except Exception:
                    stale_browser = {}
                stage = "recovery_source"
                _set_eur_source_time(user_id, markets["BTC/EUR"]["market_id"],
                                     markets["BTC/EUR"]["source_at"], stale=False)
                stage = "recovery_snapshot"
                recovered = _snapshot(user_id, markets)
                stage = "recovery_transport"
                recovered_transport = _transport_checks(user_id, recovered, runner=runner)
        stage = "after_read"
        after_business = _business_snapshot(user_id)
        stage = "validation"
        result = check_pair_score_isolation(
            owner_id=user_id, initial=initial, outage=outage, recovered=recovered,
        )
        transport = (initial_transport, outage_transport, recovered_transport)
        transport_failures = [
            f"{name}_transport_{surface}"
            for name, checks in zip(("initial", "outage", "recovered"), transport)
            for surface in ("analysis", "finn") if not checks[surface]
        ]
        if len(stale_browser) != 3 or any(code != "ok" for code in stale_browser.values()):
            transport_failures.append("outage_quote_pending_browser")
        if live_attempts:
            transport_failures.append("live_execution_attempt")
        if (before_business["counts"] != after_business["counts"]
                or before_business["fingerprints"] != after_business["fingerprints"]):
            transport_failures.append("unexpected_business_write")
        if transport_failures:
            finn_codes = {
                phase: checks["finn_codes"]
                for phase, checks in zip(("initial", "outage", "recovered"), transport)
                if checks.get("finn_codes")
            }
            finn_runtime_codes = {
                phase: checks["finn_runtime_codes"]
                for phase, checks in zip(("initial", "outage", "recovered"), transport)
                if checks.get("finn_runtime_codes")
            }
            return {"result": "FAIL", "failed_checks": sorted(set(
                result["failed_checks"] + transport_failures)),
                "pairs": 2, "phases": 3, "analysis_transport_checked": True,
                "finn_transport_checked": True, "outage_quote_pending_browser_checked": True,
                **({"finn_transport_codes": finn_codes} if finn_codes else {}),
                **({"finn_runtime_codes": finn_runtime_codes} if finn_runtime_codes else {}),
                **({"outage_browser_codes": stale_browser}
                   if any(code != "ok" for code in stale_browser.values()) else {}),
                **({"outage_browser_source_facts": browser_source_facts}
                   if browser_source_facts and any(code != "ok" for code in stale_browser.values()) else {}),
                "gate_status": "FAIL", "live_calls": len(live_attempts)}
        if result["result"] != "PASS":
            return {**result, "gate_status": "FAIL",
                    "analysis_transport_checked": True,
                    "finn_transport_checked": True,
                    "outage_quote_pending_browser_checked": True,
                    "live_calls": len(live_attempts)}
        passed = True
        return {**result, "pairs": 2, "phases": 3,
                "source_outage": "owner_scoped", "live_calls": len(live_attempts),
                "analysis_transport_checked": True,
                "finn_transport_checked": True,
                "outage_quote_pending_browser_checked": True,
                "gate_status": "PASS"}
    except Exception as error:
        if stage in {"live_guard_import", "live_guard_entry", "runner_entry"}:
            kind = type(error).__name__.lower()
            if kind not in {"importerror", "modulenotfounderror", "attributeerror",
                            "runtimeerror", "typeerror"}:
                kind = "other"
            raise RuntimeError(f"trader_pair_{stage}_{kind}_failed") from None
        if stage == "baseline":
            from backend.scripts.probe_protected_account_answer import (
                BUSINESS_MEASUREMENT_ERROR_KINDS, BUSINESS_MEASUREMENT_STAGES,
            )
            code = str(error)
            for measurement_stage in BUSINESS_MEASUREMENT_STAGES:
                for kind in BUSINESS_MEASUREMENT_ERROR_KINDS:
                    if code == f"account_safety_measurement_{measurement_stage}_{kind}_unavailable":
                        raise RuntimeError(
                            f"trader_pair_baseline_{measurement_stage}_{kind}_failed"
                        ) from None
            kind = type(error).__name__.lower()
            if kind not in {"runtimeerror", "importerror", "modulenotfounderror",
                            "attributeerror", "typeerror", "operationalerror"}:
                kind = "other"
            raise RuntimeError(f"trader_pair_baseline_unclassified_{kind}_failed") from None
        snapshot_step = str(error).removeprefix("trader_pair_snapshot_").removesuffix("_failed")
        if (stage in {"initial_snapshot", "outage_snapshot", "recovery_snapshot"}
                and snapshot_step.startswith("assessment_")
                and snapshot_step.removeprefix("assessment_") in {
                    f"{kind.lower()}_{origin}"
                    for kind in _ASSESSMENT_ERROR_KINDS | {"Other"}
                    for origin in set(_ASSESSMENT_ORIGINS.values()) | {"other"}
                }):
            raise RuntimeError(f"trader_pair_{stage}_{snapshot_step}_failed") from None
        if (stage in {"initial_snapshot", "outage_snapshot", "recovery_snapshot"}
                and str(error) == f"trader_pair_snapshot_{snapshot_step}_failed"
                and snapshot_step in {"score_builder", "assessment", "source_read",
                                      "stale_eval", "projection"}):
            raise RuntimeError(f"trader_pair_{stage}_{snapshot_step}_failed") from None
        if isinstance(error, RuntimeError) and str(error) in {
            "btc_pair_markets_unavailable", "btc_pair_source_unavailable",
            "btc_pair_fixture_source_missing", "fixture_binding_invalid",
            "fixture_has_exchange_keys",
        }:
            raise
        raise RuntimeError(f"trader_pair_{stage}_failed") from None
    finally:
        if user_id is not None and bot_id is not None:
            try:
                if passed:
                    fixture._cleanup(namespace, user_id, bot_id)
                else:
                    fixture._quarantine(namespace, user_id, bot_id)
            except Exception:
                raise RuntimeError(
                    "trader_pair_cleanup_failed" if passed else "trader_pair_quarantine_failed"
                ) from None
