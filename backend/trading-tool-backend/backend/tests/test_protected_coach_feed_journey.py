"""Fixture and output boundaries for the FINN feed-journey QA profile."""

import asyncio

import pytest

from backend.scripts import probe_protected_coach_feed_journey as probe
from backend.scripts import run_finn_production_qa as runner


NAMESPACE = "qa-44006750736-1-12345678-abcdef12"


def test_journey_profile_requires_fixture_only_permissions(monkeypatch):
    monkeypatch.setenv("FINN_QA_USER_ID", "123")
    monkeypatch.setenv("FINN_QA_ALLOW_COACH_FEED_JOURNEY_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    with pytest.raises(RuntimeError, match="feed_journey_not_authorized"):
        probe._require_run(NAMESPACE)
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    assert probe._require_run(NAMESPACE) == 123
    with pytest.raises(RuntimeError, match="feed_journey_not_authorized"):
        probe._require_run("ordinary-user")


def test_journey_runner_allowlist_never_exports_private_exception():
    assert "coach_feed_journey" in runner.ALLOWED_PROFILES
    assert runner.profile_error_category(
        "coach_feed_journey", RuntimeError("private account value"),
    ) == "feed_journey_runtime_failed"
    assert runner.profile_error_category(
        "coach_feed_journey", RuntimeError("feed_journey_report_card_missing"),
    ) == "feed_journey_report_card_missing"


def test_journey_discussion_diagnostic_is_allowlisted(monkeypatch):
    async def rejected(_user, _item, *, symbol, question, diagnostic, content_check):
        diagnostic.update({
            "turn_status": "completed", "response_present": True,
            "content_present": True, "proposal_present": False,
            "confirmation_required": False, "expected_symbol_mentioned": True,
            "error_code": "private account value",
        })
        assert not content_check("SOL is niet te beoordelen; vraag naar je setup.")
        raise RuntimeError("private account value")

    monkeypatch.setattr(probe.coach_probe, "_discuss", rejected)
    trace = {}
    with pytest.raises(RuntimeError, match="feed_journey_discuss_contract_failed"):
        asyncio.run(probe._discuss_checked(
            123, "synthetic-item", question="Bespreek SOL",
            content_checks=lambda content: probe._analysis_answer_checks(
                content, "40", "2026-11-21"), trace=trace,
        ))
    assert trace["discussion"] == {
        "turn_status": "completed", "error_code": "other",
        "response_present": True, "content_present": True,
        "proposal_present": False, "confirmation_required": False,
        "subject_mentioned": True,
        "failed_checks": ["score", "score_date"],
    }


def test_journey_discussion_runtime_failure_is_distinct(monkeypatch):
    async def failed(*_args, **_kwargs):
        raise RuntimeError("private runtime detail")

    monkeypatch.setattr(probe.coach_probe, "_discuss", failed)
    trace = {}
    with pytest.raises(RuntimeError, match="feed_journey_discuss_runtime_failed"):
        asyncio.run(probe._discuss_checked(
            123, "synthetic-item", question="Bespreek SOL",
            content_checks=lambda _content: {"score": True}, trace=trace,
        ))
    assert trace["discussion"]["turn_status"] == "unknown"
    assert trace["discussion"]["failed_checks"] == []
    assert probe._safe_discussion({"error_code": "none"})["error_code"] == "none"


def test_journey_probe_quarantines_failed_child_without_private_error(monkeypatch):
    quarantined = []
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args, **kwargs: (456, 789, "date"))
    monkeypatch.setattr(probe, "_seed_asset_only", lambda *args: (
        (_ for _ in ()).throw(RuntimeError("private account value"))
    ))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: quarantined.append(True))
    result = probe.run(NAMESPACE)
    assert quarantined == [True]
    assert result == {
        "result": "FAIL", "reason": "feed_journey_runtime_failed",
        "failure_stage": "asset_evidence", "fixture_state": "quarantined",
        "live_calls": 0,
    }


def test_journey_probe_reports_only_fixed_success_fields(monkeypatch):
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_case", lambda *args, **kwargs: {
        "result": "PASS", "analysis_ready": True, "dated_score": True,
    })
    result = probe.run(NAMESPACE)
    assert result == {
        "result": "PASS", "analysis_ready": True, "dated_score": True,
        "fixture_state": "not_created", "live_calls": 0,
    }


def test_journey_answer_checks_require_dated_score_and_current_report_distinction():
    assert probe._analysis_answer_valid(
        "SOL heeft een benchmark van 0/100 op 21 november 2026. "
        "De score is geverifieerd. Bespreek eerst de setupvoorwaarden.",
        "0", "2026-11-21",
    )
    assert probe._analysis_answer_valid(
        "Voor SOL is de opnieuw geverifieerde benchmark 40/100 per "
        "21 november 2026. Volgende setupstap: bepaal de voorwaarden.",
        "40", "2026-11-21",
    )
    assert probe._analysis_answer_valid(
        "SOL heeft een actuele, brongeverifieerde benchmarkscore van "
        "40/100 op 21 november 2026. Bepaal de setupvoorwaarden.",
        "40", "2026-11-21",
    )
    assert probe._analysis_answer_valid(
        "Voor SOL is de benchmarkscore 40/100 per 21 november 2026. "
        "Bespreek de setupvoorwaarden als volgende stap.",
        "40", "2026-11-21",
    )
    assert not probe._analysis_answer_valid(
        "Voor SOL is de benchmarkscore 40/100 per 20 november 2026. "
        "Bespreek de setupvoorwaarden als volgende stap.",
        "40", "2026-11-21",
    )
    assert not probe._analysis_answer_valid(
        "SOL heeft een setup nodig; de score kan ik niet verifiëren.",
        "0", "2026-11-21",
    )
    assert not probe._analysis_answer_valid(
        "De huidige SOL-score 40/100 van 21 november 2026 is niet verifieerbaar; "
        "bespreek de setup.", "40", "2026-11-21",
    )
    assert not probe._analysis_answer_valid(
        "SOL: benchmark 40/100 op 21 november 2026. De benchmark is niet "
        "beschikbaar; bekijk de setup.", "40", "2026-11-21",
    )
    assert not probe._analysis_answer_valid(
        "SOL: score 40/100 op 21 november 2026 lijkt actueel, maar is niet "
        "betrouwbaar. Bespreek de setup.", "40", "2026-11-21",
    )
    assert probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bewaart 40/100 in de "
        "snapshot. De huidige marktscore ontbreekt; een actuele totaalscore is "
        "niet beschikbaar.", "40", "2026-11-21",
    )
    assert probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bevat in zijn "
        "rapportsnapshot een benchmarkscore van 40. De huidige marktscore "
        "ontbreekt; de volledige huidige benchmarkscore is niet beschikbaar.",
        "40", "2026-11-21",
    )
    assert probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bevat een "
        "benchmarkscore van 40 in de rapportsnapshot. De huidige "
        "scorecontrole heeft geen opgeslagen marktscore; daarom is er "
        "geen complete benchmarkscore.", "40", "2026-11-21",
    )
    assert probe._report_answer_valid(
        "Het dagrapport van 21 november 2026 bevat voor SOL een "
        "rapportsnapshot-benchmark van 40. De huidige scorelezing is anders: "
        "een marktscore ontbreekt, dus er is geen volledige huidige benchmark.",
        "40", "2026-11-21",
    )
    assert probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 heeft een "
        "rapport-snapshot met benchmarkscore van 40. De huidige marktscore "
        "ontbreekt; er is geen huidige totaalscore om met de rapportscore "
        "van 40 te vergelijken.", "40", "2026-11-21",
    )
    assert not probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bewaart 40/100 in de "
        "snapshot. De actuele benchmark is ook 40/100.", "40", "2026-11-21",
    )
    assert not probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bewaart 40/100 in de "
        "snapshot. De huidige score is ook 40/100, geen probleem.",
        "40", "2026-11-21",
    )
    assert not probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bewaart 40/100 in de "
        "snapshot. De marktscore ontbreekt, maar de huidige score is 40/100.",
        "40", "2026-11-21",
    )
    assert not probe._report_answer_valid(
        "Het dagrapport voor SOL van 21 november 2026 bewaart 40/100 in de "
        "snapshot. De marktscore ontbreekt, maar de huidige benchmark is ook "
        "40/100.", "40", "2026-11-21",
    )
    assert not probe._report_answer_valid(
        "SOL: het rapport is beschikbaar, maar de actuele score niet.",
        "40", "2026-11-21",
    )
