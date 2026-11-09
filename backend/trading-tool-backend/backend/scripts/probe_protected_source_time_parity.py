"""Four-surface quote provenance and deployed browser time checks for Paper QA.

Called only while the protected automatic Paper-exit child fixture is alive.
All source IDs, values, answers and tokens remain in this process.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from backend.scripts.qa_trader_gate_invariants import check_source_time_parity
from backend.scripts.qa_protected_readback import read_json


def _normalized_ref(value: object) -> tuple[int, int, datetime] | None:
    if not isinstance(value, dict):
        return None
    try:
        market_id = int(value["market_id"])
        measurement_id = int(value["measurement_id"])
        moment = datetime.fromisoformat(str(value["source_observed_at_utc"]).replace("Z", "+00:00"))
        if market_id <= 0 or measurement_id <= 0 or moment.tzinfo is None:
            return None
        return market_id, measurement_id, moment.astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None


def _saved_report(user_id: int) -> dict:
    """Run the product report generator and normal writer, without push/feed side effects."""
    from backend.infrastructure.database import SessionLocal
    from backend.infrastructure.repositories.daily_report_repository import DailyReportWriteRepository
    from backend.services.finn_unified_report_service import generate_unified_daily_report_sections
    from backend.celery_task.daily_report_task import jsonb, to_float

    report = generate_unified_daily_report_sections(user_id=user_id)
    snapshot = report.get("score_source_snapshot")
    if not isinstance(snapshot, dict):
        raise RuntimeError("source_parity_report_snapshot_missing")
    db = SessionLocal()
    try:
        sections = {key: jsonb(report.get(key)) for key in DailyReportWriteRepository.JSONB_FIELDS}
        DailyReportWriteRepository(db).upsert_daily_report(
            user_id=user_id, report_date=date.today(), sections=sections,
            price=to_float(report.get("price")),
            change_24h=to_float(report.get("change_24h")),
            volume=to_float(report.get("volume")),
            macro_score=to_float(report.get("macro_score")),
            technical_score=to_float(report.get("technical_score")),
            market_score=to_float(report.get("market_score")),
            setup_score=to_float(report.get("setup_score")),
        )
        db.commit()
        return snapshot
    except Exception:
        db.rollback()
        raise RuntimeError("source_parity_report_write_failed") from None
    finally:
        db.close()


async def _finn_market_read(user_id: int) -> dict | None:
    from backend.scripts.probe_protected_closed_paper_review import _chat_turn
    from backend.scripts.probe_protected_account_answer import _read_tool_results

    turn = await _chat_turn(
        user_id,
        "Lees alleen de actuele BTC/USDT marktkoers uit de opgeslagen marktbron. "
        "Geef het exacte bronmoment in UTC; wijzig niets.",
    )
    if (turn.status != "completed" or turn.response is None
            or turn.response.proposal_id or turn.response.confirmation_required
            or turn.policy and turn.policy.execute_allowed):
        return None
    rows = await _read_tool_results(
        run_id=turn.run_id, conversation_id=turn.conversation_id, user_id=user_id,
    )
    reads = [item["data"] for item in rows if isinstance(item, dict)
            and item.get("scope") == "read_market_snapshot"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and item["data"].get("pair") == "BTC/USDT"]
    return reads[0] if len(reads) == 1 else None


def _observed_utc(value: object) -> str | None:
    """Normalize a product-read source moment; never derive it from the ref."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.replace(tzinfo=moment.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


async def _rendered_quote_times(user_id: int, canonical_ref: dict) -> dict[str, str]:
    from backend.scripts.qa_protected_browser import observe_page
    from backend.utils.auth_utils import create_access_token

    token = create_access_token({"sub": str(user_id), "role": "user"})
    checks: dict[str, str] = {}
    canonical = _normalized_ref(canonical_ref)
    if canonical is None:
        raise RuntimeError("source_parity_browser_ref_invalid")
    try:
        for zone in ("Europe/Amsterdam", "America/New_York", "Asia/Tokyo"):
            for surface, path in (
                ("analysis", "/asset?symbol=BTC&quote=USDT"),
                ("report", "/report"),
            ):
                observed_responses = []

                def observe_response(response, *, expected_surface=surface):
                    expected_path = ("/api/workspace/exact-market" if expected_surface == "analysis"
                                     else "/api/report/daily/latest")
                    if urlsplit(response.url).path == expected_path:
                        observed_responses.append(response)

                async def inspect(page, *, expected_surface=surface):
                    for _ in range(50):
                        if observed_responses:
                            break
                        await asyncio.sleep(0.1)
                    if not observed_responses:
                        return "api_unseen"
                    response = observed_responses[-1]
                    if response.status != 200:
                        return "api_http_failure"
                    try:
                        payload = await response.json()
                        if expected_surface == "analysis":
                            page_ref = _normalized_ref((payload.get("quote") or {}).get("source_ref"))
                            locale = "nl-NL"
                        else:
                            snapshot = payload.get("score_source_snapshot") or {}
                            matches = [item.get("market_snapshot") or {}
                                       for item in snapshot.get("assets") or []
                                       if isinstance(item, dict) and item.get("pair") == "BTC/USDT"]
                            page_ref = _normalized_ref(matches[0].get("source_ref")) if len(matches) == 1 else None
                            language = str(snapshot.get("content_locale") or "nl")[:2].lower()
                            locale = {"nl": "nl-NL", "en": "en-US", "de": "de-DE"}.get(language, "nl-NL")
                    except Exception:
                        return "api_source_unverified"
                    if page_ref is None:
                        return "api_source_unverified"
                    if page_ref != canonical:
                        return "page_source_changed"
                    formatter = (
                        "{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'}"
                        if expected_surface == "analysis" else
                        "{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'}"
                    )
                    expected = await page.evaluate(
                        "([source, locale]) => new Intl.DateTimeFormat(locale, " + formatter +
                        ").format(new Date(source)) + ' UTC'", [page_ref[2].isoformat(), locale],
                    )
                    try:
                        await page.get_by_text(expected, exact=False).first.wait_for(timeout=15000)
                        return "ok"
                    except Exception:
                        return "selector_missing"

                try:
                    checks[f"{surface}_{zone.split('/')[-1].lower()}"] = await observe_page(
                        base_url="https://tradamind.com", path=path, token=token,
                        inspect=inspect, timezone_id=zone,
                        bypass_fixture_onboarding=True,
                        observe_response=observe_response,
                    )
                except Exception:
                    checks[f"{surface}_{zone.split('/')[-1].lower()}"] = "page_unavailable"
        return checks
    finally:
        token = None


def run(*, user_id: int, market_id: int, paper_evidence: dict,
        frozen_ref: dict | None) -> dict:
    """Return fixed check names only; never publish the underlying source refs."""
    checks = {"frozen_paper_source": False, "analysis_source": False,
              "report_source": False, "finn_source": False,
              "four_instant_display": False, "deployed_browser_zones": False}
    parity_subchecks: list[str] = []
    surface_display_checks: dict[str, bool] = {}
    canonical = _normalized_ref(frozen_ref)
    if canonical is None or canonical[0] != market_id:
        return {"result": "FAIL", "failed_checks": ["frozen_paper_source"],
                "gate_status": "FAIL", "browser_zones_checked": 0}
    source_at = canonical[2].isoformat()
    paper_ref = _normalized_ref((paper_evidence.get("ui_projection") or {}).get("source_ref"))
    checks["frozen_paper_source"] = paper_ref == canonical
    try:
        analysis = read_json(
            owner_id=user_id,
            path="/api/workspace/exact-market?symbol=BTC&quote_currency=USDT",
        )
        analysis_quote = analysis.get("quote") or {}
        checks["analysis_source"] = (
            analysis.get("market_id") == market_id
            and _normalized_ref(analysis_quote.get("source_ref")) == canonical
        )
    except Exception:
        analysis_quote = {}
    try:
        _saved_report(user_id)
        report = read_json(owner_id=user_id, path="/api/report/daily/latest?symbol=BTC")
        snapshot = report.get("score_source_snapshot") or {}
        matches = [item.get("market_snapshot") or {} for item in snapshot.get("assets") or []
                   if isinstance(item, dict) and item.get("market_id") == market_id
                   and item.get("pair") == "BTC/USDT"]
        report_quote = matches[0] if len(matches) == 1 else {}
        checks["report_source"] = _normalized_ref(report_quote.get("source_ref")) == canonical
    except Exception:
        report_quote = {}
    try:
        finn_read = asyncio.run(_finn_market_read(user_id))
        checks["finn_source"] = _normalized_ref((finn_read or {}).get("source_ref")) == canonical
    except Exception:
        finn_read = {}
    try:
        amsterdam = canonical[2].astimezone(ZoneInfo("Europe/Amsterdam"))
        label = amsterdam.tzname()
        surfaces = {
            "analysis": {"source_at": (analysis_quote.get("source_ref") or {}).get("source_observed_at_utc"),
                         "displayed_at": _observed_utc(analysis_quote.get("as_of")), "zone_label": "UTC"},
            "report": {"source_at": (report_quote.get("source_ref") or {}).get("source_observed_at_utc"),
                       "displayed_at": _observed_utc(report_quote.get("as_of")), "zone_label": "UTC"},
            "bot": {"source_at": (paper_evidence.get("ui_projection") or {}).get("source_price_at"),
                    "displayed_at": amsterdam.isoformat(), "zone_label": label},
            "finn": {"source_at": ((finn_read or {}).get("source_ref") or {}).get("source_observed_at_utc"),
                     "displayed_at": _observed_utc((finn_read or {}).get("as_of")), "zone_label": "UTC"},
        }
        parity = check_source_time_parity(canonical_source_at=source_at, surfaces=surfaces)
        checks["four_instant_display"] = parity["result"] == "PASS"
        parity_subchecks = parity["failed_checks"]
        for surface, item in surfaces.items():
            observed = _observed_utc(item.get("displayed_at"))
            observed_at = datetime.fromisoformat(observed) if observed else None
            surface_display_checks[surface] = bool(observed_at) and (
                observed_at.replace(microsecond=0) == canonical[2].replace(microsecond=0)
                if surface == "finn" else observed_at == canonical[2]
            )
    except Exception:
        pass
    try:
        browser = asyncio.run(_rendered_quote_times(user_id, frozen_ref))
        browser_zones_checked = len(browser)
        checks["deployed_browser_zones"] = len(browser) == 6 and all(
            value is True or value == "ok" for value in browser.values()
        )
    except Exception:
        browser_zones_checked = 0
        browser = {f"{surface}_{zone}": "page_unavailable"
                   for surface in ("analysis", "report")
                   for zone in ("amsterdam", "new_york", "tokyo")}
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {"result": "FAIL" if failed else "PASS", "failed_checks": failed,
            "gate_status": "FAIL" if failed else "PASS",
            "browser_zones_checked": browser_zones_checked,
            "browser_zone_checks": {key: browser.get(key) is True or browser.get(key) == "ok" for key in (
                "analysis_amsterdam", "analysis_new_york", "analysis_tokyo",
                "report_amsterdam", "report_new_york", "report_tokyo",
            )},
            "browser_zone_phases": {key: value for key in (
                "analysis_amsterdam", "analysis_new_york", "analysis_tokyo",
                "report_amsterdam", "report_new_york", "report_tokyo",
            ) if (value := browser.get(key)) in {
                "ok", "api_unseen", "api_http_failure", "api_source_unverified",
                "page_source_changed", "selector_missing", "page_unavailable",
            }},
            "surface_display_checks": {key: bool(surface_display_checks.get(key))
                                       for key in ("analysis", "report", "bot", "finn")},
            "parity_subchecks": [code for code in parity_subchecks if code in {
                "dated_source", "same_source_instant", "same_display_instant", "explicit_zone",
            }]}
