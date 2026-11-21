"""Bounded QA child for a newly published analysis and report feed journey.

Only the protected production QA runner may call this probe. Its synthetic,
inactive owner has no exchange credentials and cannot trade. Shared market
data and normal user records remain untouched. The sanitized result contains
only fixed check names and booleans.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.scripts import probe_protected_coach_feed as coach_probe
from backend.scripts import probe_protected_score2_stale_paper as fixture


SAFE_FAILURES = frozenset({
    "feed_journey_not_authorized", "feed_journey_owner_scope_failed",
    "feed_journey_score_unavailable", "feed_journey_analysis_card_missing",
    "feed_journey_invalid_score_visible", "feed_journey_report_card_missing",
    "feed_journey_discuss_failed", "feed_journey_discuss_runtime_failed",
    "feed_journey_discuss_contract_failed", "feed_journey_unexpected_write",
    "feed_journey_cleanup_failed", "feed_journey_quarantine_failed",
    "feed_journey_runtime_failed",
})
_MONTHS_NL = (
    "", "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
)
_ANSWER_CHECKS = frozenset({
    "subject", "score", "score_date", "setup_step",
    "no_score_denial", "snapshot_score", "report_date", "report", "snapshot",
    "current_incomplete", "no_current_score_claim",
})
_REPORT_SUBSTAGES = frozenset({
    "release_async_connections", "connect", "owner_scope", "insert", "commit",
    "feed_publish", "card_readback",
})
_ASSET_SUBSTAGES = frozenset({
    "connect", "owner_scope", "exchange_keys", "watchlist_insert",
    "indicator_config_copy", "macro_reading_copy", "technical_reading_copy",
    "market_reading_copy", "setup_scope", "commit",
})
_REPORT_SQLSTATES = {
    "23502": "not_null", "23503": "foreign_key", "23505": "duplicate",
    "42703": "missing_column", "42P01": "missing_table",
    "42804": "type_mismatch", "22P02": "invalid_text",
    "40P01": "deadlock", "55P03": "lock_unavailable",
}


def _safe_error_category(error: Exception) -> str:
    category = "other"
    for candidate in (error, getattr(error, "orig", None),
                      getattr(error, "__cause__", None)):
        code = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if code in _REPORT_SQLSTATES:
            category = _REPORT_SQLSTATES[code]
            break
    return category


def _safe_report_failure(error: Exception, trace: dict) -> dict[str, str]:
    stage = trace.get("report_substage")
    return {"substage": stage if stage in _REPORT_SUBSTAGES else "unknown",
            "error_category": _safe_error_category(error)}


def _safe_asset_failure(error: Exception, trace: dict) -> dict[str, str]:
    stage = trace.get("asset_substage")
    return {"substage": stage if stage in _ASSET_SUBSTAGES else "unknown",
            "error_category": _safe_error_category(error)}


def _score_in_answer(content: str, score: str) -> bool:
    lower = content.casefold()
    score_matches = re.findall(r"(?<!\d)(\d{1,3}(?:[,.]\d+)?)\s*/\s*100\b", lower)
    score_matches += re.findall(
        r"\b(?:benchmarkscore|benchmark)\b\s+(?:van|is|bedraagt)\s+\*{0,2}"
        r"(\d{1,3}(?:[,.]\d+)?)\b", lower,
    )
    return any(Decimal(value.replace(",", ".")) == Decimal(score)
               for value in score_matches)


def _date_in_answer(content: str, source_date: str) -> bool:
    observed = date.fromisoformat(source_date)
    lower = content.casefold()
    return (source_date in lower or
            f"{observed.day} {_MONTHS_NL[observed.month]} {observed.year}" in lower)


def _analysis_answer_checks(content: str, score: str, source_date: str) -> dict[str, bool]:
    lower = content.casefold()
    denied = re.search(
        r"\b(?:score|benchmark)\b.{0,70}"
        r"\b(?:niet beschikbaar|niet verifieerbaar|niet geverifieerd|"
        r"niet betrouwbaar|onbetrouwbaar|ontbreekt)\b",
        lower, re.DOTALL,
    )
    return {
        "subject": "sol" in lower,
        "score": _score_in_answer(content, score),
        "score_date": _date_in_answer(content, source_date),
        "setup_step": "setup" in lower,
        "no_score_denial": denied is None and "geen actuele score" not in lower,
    }


def _analysis_answer_valid(content: str, score: str, source_date: str) -> bool:
    return all(_analysis_answer_checks(content, score, source_date).values())


def _report_answer_checks(content: str, score: str, source_date: str) -> dict[str, bool]:
    lower = content.casefold()
    current_missing = (
        re.search(r"\b(?:marktscore|marktcomponent)\s+(?:is\s+)?"
                  r"(?:ontbreekt|niet beschikbaar|onvolledig)\b", lower)
        or re.search(r"\b(?:huidige|actuele)\s+(?:totaal|benchmark)?score"
                     r"\s+(?:is\s+)?(?:niet beschikbaar|onvolledig|ontbreekt)\b", lower)
        or (re.search(r"\b(?:huidig|actueel)\w*\b", lower)
            and re.search(r"\bgeen\s+(?:(?:opgeslagen|complete|volledige)\s+)*"
                          r"(?:markt|benchmark|totaal)score\b", lower))
    )
    contradictory_current = re.search(
        r"\b(?:huidige|actuele)\s+"
        r"(?:totaalscore|benchmarkscore|score|benchmark)\b"
        r"\s*(?::|=|is(?:\s+ook)?|bedraagt|van)\s*\*{0,2}"
        r"\d{1,3}(?:[,.]\d+)?(?:\s*/\s*100)?\b",
        lower,
    )
    return {
        "subject": "sol" in lower,
        "snapshot_score": _score_in_answer(content, score),
        "report_date": _date_in_answer(content, source_date),
        "report": "rapport" in lower,
        "snapshot": "snapshot" in lower or "momentopname" in lower,
        "current_incomplete": current_missing is not None,
        "no_current_score_claim": contradictory_current is None,
    }


def _report_answer_valid(content: str, score: str, source_date: str) -> bool:
    return all(_report_answer_checks(content, score, source_date).values())


def _safe_discussion(diagnostic: dict) -> dict:
    status = diagnostic.get("turn_status")
    return {
        "turn_status": status if status in coach_probe.TURN_STATUSES else "unknown",
        "error_code": diagnostic.get("error_code")
        if diagnostic.get("error_code") in coach_probe.SAFE_TURN_ERROR_CODES | {"none", "other"}
        else "other" if diagnostic.get("error_code") else "none",
        "response_present": diagnostic.get("response_present") is True,
        "content_present": diagnostic.get("content_present") is True,
        "proposal_present": diagnostic.get("proposal_present") is True,
        "confirmation_required": diagnostic.get("confirmation_required") is True,
        "subject_mentioned": diagnostic.get("expected_symbol_mentioned") is True,
        "failed_checks": sorted(name for name in diagnostic.get("failed_checks", [])
                                if name in _ANSWER_CHECKS),
    }


async def _discuss_checked(user_id: int, item_id: str, *, question: str,
                           content_checks, trace: dict) -> None:
    diagnostic: dict = {}

    def check_answer(content: str) -> bool:
        checks = content_checks(content)
        diagnostic["failed_checks"] = [name for name, passed in checks.items()
                                       if not passed]
        return all(checks.values())

    try:
        await coach_probe._discuss(user_id, item_id, symbol="SOL",
                                   question=question, diagnostic=diagnostic,
                                   content_check=check_answer)
    except Exception:
        trace["discussion"] = _safe_discussion(diagnostic)
        reason = ("feed_journey_discuss_contract_failed"
                  if diagnostic.get("turn_status") == "completed" else
                  "feed_journey_discuss_runtime_failed")
        raise RuntimeError(reason) from None


@contextmanager
def _guard_live_exchange():
    from backend.engine import trading_bot_execution as execution

    original = execution._execute_on_exchange_sync
    attempts: list[bool] = []

    def blocked(*_args, **_kwargs):
        attempts.append(True)
        raise RuntimeError("feed_journey_unexpected_write")

    execution._execute_on_exchange_sync = blocked
    try:
        yield attempts
    finally:
        execution._execute_on_exchange_sync = original


def _require_run(namespace: str) -> int:
    if (os.getenv("FINN_QA_ALLOW_COACH_FEED_JOURNEY_FIXTURE") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") == "1"
            or not fixture.NAMESPACE_PATTERN.fullmatch(namespace)):
        raise RuntimeError("feed_journey_not_authorized")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("feed_journey_not_authorized")
    return int(bound)


def _seed_asset_only(user_id: int, namespace: str, trace: dict) -> None:
    """Copy only the child owner's dated ETH readings to an unplanned SOL asset."""
    trace["report_substage"] = "connect"
    trace["asset_substage"] = "connect"
    connection = fixture._connection()
    try:
        trace["asset_substage"] = "owner_scope"
        with connection.cursor() as cursor:
            cursor.execute("""SELECT is_active,ai_preferences FROM users
                              WHERE id=%s FOR UPDATE""", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] is not False
                    or (owner[1] or {}).get("qa_fixture") != fixture.FIXTURE_MARKER
                    or (owner[1] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("feed_journey_owner_scope_failed")
            trace["asset_substage"] = "exchange_keys"
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            if cursor.fetchone()[0]:
                raise RuntimeError("feed_journey_owner_scope_failed")
            trace["asset_substage"] = "watchlist_insert"
            cursor.execute("""INSERT INTO watchlists (user_id,symbol,created_at)
                              VALUES (%s,'SOL',NOW())""", (user_id,))
            trace["asset_substage"] = "indicator_config_copy"
            cursor.execute("""INSERT INTO user_indicator_configs
                (user_id,indicator,category,symbol,asset_class,priority,enabled,created_at,updated_at)
                SELECT user_id,indicator,category,'SOL',asset_class,priority,enabled,created_at,updated_at
                FROM user_indicator_configs WHERE user_id=%s AND symbol='ETH'
                  AND market_id IS NULL""", (user_id,))
            for table, column in (("macro_data", "name"),
                                  ("technical_indicators", "indicator"),
                                  ("market_data_indicators", "name")):
                trace["asset_substage"] = {
                    "macro_data": "macro_reading_copy",
                    "technical_indicators": "technical_reading_copy",
                    "market_data_indicators": "market_reading_copy",
                }[table]
                # The original stale-score fixture deliberately ages its
                # market reading. This child needs a current synthetic
                # measurement to exercise a *verified* analysis card.
                source_time = ("NOW()" if table == "market_data_indicators"
                               else "source_observed_at")
                market_scope = ("" if table == "macro_data" else " AND market_id IS NULL")
                cursor.execute(f"""INSERT INTO {table}
                    (user_id,symbol,{column},value,timestamp,source_observed_at)
                    SELECT user_id,'SOL',{column},value,{source_time},{source_time}
                    FROM {table} WHERE user_id=%s AND symbol='ETH'{market_scope}""",
                    (user_id,))
            trace["asset_substage"] = "setup_scope"
            cursor.execute("SELECT COUNT(*) FROM setups WHERE user_id=%s AND symbol='SOL'", (user_id,))
            if cursor.fetchone()[0]:
                raise RuntimeError("feed_journey_owner_scope_failed")
        trace["asset_substage"] = "commit"
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def _card(user_id: int, kind: str) -> dict:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async with async_session_factory() as session:
        feed = FinnCoachFeedService(session)
        items = [item for item in await feed.list(user_id=user_id)
                 if item.get("event_type") == kind]
        if len(items) != 1:
            raise RuntimeError("feed_journey_analysis_card_missing" if kind == "analysis_ready"
                               else "feed_journey_report_card_missing")
        item = await feed.detail(user_id=user_id, item_id=str(items[0]["id"]))
        other = await feed.detail(user_id=user_id + 1, item_id=str(items[0]["id"]))
        if not item or other is not None:
            raise RuntimeError("feed_journey_owner_scope_failed")
        return item


async def _analysis(user_id: int) -> tuple[str, str, str]:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService
    from backend.services.setup_market_match_service import SetupMarketMatchService

    async with async_session_factory() as session:
        assessment = await SetupMarketMatchService(session).for_asset(user_id, "SOL", setups=[])
        if assessment.get("source_status") != "available":
            raise RuntimeError("feed_journey_score_unavailable")
        score = assessment.get("benchmark_score")
        moment = assessment.get("as_of")
        if (score is None or not isinstance(moment, date)
                or moment != datetime.now(timezone.utc).date()):
            raise RuntimeError("feed_journey_score_unavailable")
        created = await FinnCoachFeedService(session).reconcile_journey_next_steps(
            user_id=user_id, symbol="SOL",
        )
        await session.commit()
        if len(created) != 1:
            raise RuntimeError("feed_journey_analysis_card_missing")
    item = await _card(user_id, "analysis_ready")
    evidence = item.get("evidence") or {}
    body = str(item.get("description") or "")
    saved_value = evidence.get("benchmark_score")
    score_text = "" if saved_value is None else str(saved_value)
    source_date = moment.isoformat()
    if (evidence.get("symbol") != "SOL" or evidence.get("score_as_of") != source_date
            or not score_text or score_text not in body or source_date not in body):
        raise RuntimeError("feed_journey_analysis_card_missing")
    return str(item["id"]), score_text, source_date


async def _invalidate_score(user_id: int) -> None:
    from sqlalchemy import text
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async with async_session_factory() as session:
        changed = await session.execute(text("""UPDATE daily_scores SET market_score=NULL
            WHERE user_id=:user_id AND symbol='SOL' AND market_id IS NULL
              AND report_date=CURRENT_DATE"""), {"user_id": user_id})
        if changed.rowcount != 1:
            raise RuntimeError("feed_journey_score_unavailable")
        await FinnCoachFeedService(session).reconcile_journey_next_steps(
            user_id=user_id, symbol="SOL",
        )
        await session.commit()
        items = await FinnCoachFeedService(session).list(user_id=user_id)
        if any(item.get("event_type") == "analysis_ready" for item in items):
            raise RuntimeError("feed_journey_invalid_score_visible")


def _store_report(user_id: int, namespace: str, score: str, source_date: str,
                  trace: dict) -> dict:
    from backend.celery_task.daily_report_task import _publish_daily_report_ready_feed

    report_date = datetime.now(timezone.utc).date()
    snapshot = {"assets": [{"symbol": "SOL", "pair": "SOL",
                            "score_status": "available",
                            "benchmark_score": float(score),
                            "score_as_of": source_date}]}
    report = {"score_source_snapshot": snapshot}
    connection = fixture._connection()
    try:
        trace["report_substage"] = "owner_scope"
        with connection.cursor() as cursor:
            cursor.execute("""SELECT is_active,ai_preferences FROM users
                              WHERE id=%s FOR UPDATE""", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] is not False
                    or (owner[1] or {}).get("qa_fixture") != fixture.FIXTURE_MARKER
                    or (owner[1] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("feed_journey_owner_scope_failed")
            trace["report_substage"] = "insert"
            cursor.execute("""INSERT INTO daily_reports
                (user_id,report_date,score_source_snapshot)
                VALUES (%s,%s,%s::jsonb)""",
                (user_id, report_date, json.dumps(snapshot)))
        trace["report_substage"] = "commit"
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    trace["report_substage"] = "feed_publish"
    _publish_daily_report_ready_feed(user_id, report_date, report)
    return {"report_date": report_date.isoformat(), "attention_pair": "SOL"}


def _case(namespace: str, bound: int, *, run_async, trace: dict) -> dict:
    user_id = bot_id = None
    passed = False
    try:
        trace["stage"] = "seed"
        user_id, bot_id, _ = fixture._seed(namespace, bound, bot_active=False)
        trace["fixture_state"] = "created"
        trace["stage"] = "asset_evidence"
        _seed_asset_only(user_id, namespace, trace)
        from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user
        trace["stage"] = "score_build"
        build_daily_scores_for_user(user_id, ["SOL"], publish_feed=False)
        trace["stage"] = "analysis_publish"
        analysis_id, saved_score, source_date = run_async(_analysis(user_id))
        trace["stage"] = "analysis_discuss"
        run_async(_discuss_checked(
            user_id, analysis_id,
            question="Bespreek deze analyse voor SOL. Lees de actuele score en bronnen "
                     "opnieuw en adviseer één volgende setupstap. Maak niets aan.",
            content_checks=lambda content: _analysis_answer_checks(
                content, saved_score, source_date),
            trace=trace,
        ))
        trace["stage"] = "score_invalidate"
        run_async(_invalidate_score(user_id))
        trace["stage"] = "report_publish"
        # The production publisher owns a fresh synchronous Celery event loop.
        # Release connections from this probe's loop before calling it.
        from backend.infrastructure.database import engine
        trace["report_substage"] = "release_async_connections"
        run_async(engine.dispose())
        report = _store_report(user_id, namespace, saved_score, source_date, trace)
        trace["report_substage"] = "card_readback"
        item = run_async(_card(user_id, "daily_report_ready"))
        evidence = item.get("evidence") or {}
        if (evidence.get("report_date") != report["report_date"]
                or evidence.get("attention_pair") != "SOL"
                or evidence.get("attention_kind") != "benchmark_available"
                or "dagrapport" not in str(item.get("title") or "").casefold()
                or "SOL" not in str(item.get("description") or "")
                or report["report_date"] not in str(item.get("description") or "")
                or not item.get("source_observed_at")):
            raise RuntimeError("feed_journey_report_card_missing")
        trace["stage"] = "report_discuss"
        run_async(_discuss_checked(
            user_id, str(item["id"]),
            question=f"Bespreek het opgeslagen dagrapport van {report['report_date']} voor SOL. "
                     "Maak onderscheid tussen de rapportsnapshot en de huidige score. Wijzig niets.",
            content_checks=lambda content: _report_answer_checks(
                content, saved_score, report["report_date"]),
            trace=trace,
        ))
        trace["stage"] = "safety"
        if coach_probe._counts(user_id) != (0, 0, 0, 0):
            raise RuntimeError("feed_journey_unexpected_write")
        passed = True
        return {"result": "PASS", "analysis_ready": True,
                "dated_score": True, "invalid_score_hidden": True,
                "report_attention": True, "analysis_discuss": True,
                "report_discuss": True, "read_only_discussions": True}
    finally:
        if user_id is not None and bot_id is not None:
            try:
                if passed:
                    fixture._cleanup(namespace, user_id, bot_id, require_safe_pair_cleanup=True)
                    trace["fixture_state"] = "cleaned"
                else:
                    fixture._quarantine(namespace, user_id, bot_id)
                    trace["fixture_state"] = "quarantined"
            except Exception:
                trace["fixture_state"] = "cleanup_failed"
                raise RuntimeError("feed_journey_cleanup_failed" if passed else
                                   "feed_journey_quarantine_failed") from None


def run(namespace: str) -> dict:
    bound = _require_run(namespace)
    from backend.infrastructure.database import engine
    trace = {"stage": "preflight", "fixture_state": "not_created"}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with _guard_live_exchange() as live_attempts:
            try:
                result = _case(namespace, bound, run_async=loop.run_until_complete,
                               trace=trace)
                result["fixture_state"] = trace["fixture_state"]
            except Exception as error:
                code = str(error)
                result = {"result": "FAIL", "reason": code if code in SAFE_FAILURES
                          else "feed_journey_runtime_failed",
                          "failure_stage": trace["stage"],
                          "fixture_state": trace["fixture_state"]}
                if trace["stage"] in {"analysis_discuss", "report_discuss"}:
                    result["discussion"] = trace.get("discussion", _safe_discussion({}))
                if trace["stage"] == "report_publish":
                    result["report_failure"] = _safe_report_failure(error, trace)
                if trace["stage"] == "asset_evidence":
                    result["asset_failure"] = _safe_asset_failure(error, trace)
            if live_attempts:
                result = {"result": "FAIL", "reason": "feed_journey_unexpected_write",
                          "failure_stage": trace["stage"],
                          "fixture_state": trace["fixture_state"]}
            result["live_calls"] = len(live_attempts)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
    return result
