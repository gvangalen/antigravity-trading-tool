import asyncio
from types import SimpleNamespace

from backend.services import ai_assistant_service as assistant_module
from backend.services import finn_plan_service as finn_module
from backend.services import report_service as report_module
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.finn_plan_service import FinnPlanService
from backend.services.report_service import ReportService


def test_mission_control_preview_cache_reuses_base_analysis_and_invalidates(monkeypatch):
    finn_module._mission_control_preview_cache.clear()
    service = FinnPlanService(None)
    calls = {"count": 0}

    async def fake_load(user_id, *, mission_control_fast, mission_control_preview_only):
        calls["count"] += 1
        return {
            "has_any_scores": True,
            "blocked_assets": [],
            "warning_assets": [],
            "reasons": [],
            "suggested_actions": [],
        }

    monkeypatch.setattr(service, "_load_portfolio_daily_coach_base_analysis", fake_load)
    monkeypatch.setattr(service, "_portfolio_question_focus", lambda query: "headline")
    monkeypatch.setattr(service, "_portfolio_daily_coach_message", lambda analysis: "daily-coach-preview")

    first = asyncio.run(service.build_portfolio_daily_coach_response(
        7,
        "Geef mijn daily brief",
        {"scope": "mission_control", "mission_control_fast": True, "mission_control_preview_only": True},
    ))
    second = asyncio.run(service.build_portfolio_daily_coach_response(
        7,
        "Geef mijn daily brief",
        {"scope": "mission_control", "mission_control_fast": True, "mission_control_preview_only": True},
    ))

    assert first["response"] == "daily-coach-preview"
    assert second["response"] == "daily-coach-preview"
    assert calls["count"] == 1

    FinnPlanService.invalidate_runtime_caches_for_user(7)

    asyncio.run(service.build_portfolio_daily_coach_response(
        7,
        "Geef mijn daily brief",
        {"scope": "mission_control", "mission_control_fast": True, "mission_control_preview_only": True},
    ))

    assert calls["count"] == 2


def test_recent_governance_events_cache_reuses_same_window():
    finn_module._governance_event_cache.clear()

    class _Row:
        def __init__(self, mapping):
            self._mapping = mapping

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt, params):
            self.calls += 1
            return _Result([
                _Row({
                    "id": 1,
                    "type": "finn_priority_engine_summary",
                    "symbol": "BTC",
                    "title": "Priority",
                    "description": "Review BTC first",
                    "severity": "info",
                    "payload": '{"headline":"Review BTC first"}',
                    "status": "open",
                    "created_at": "2026-06-06T09:00:00Z",
                })
            ])

    session = _Session()
    service = FinnPlanService(session)

    first = asyncio.run(service._fetch_recent_governance_events(
        9,
        event_types=["finn_priority_engine_summary"],
        limit=20,
    ))
    second = asyncio.run(service._fetch_recent_governance_events(
        9,
        event_types=["finn_priority_engine_summary"],
        limit=20,
    ))

    assert session.calls == 1
    assert first == second
    assert first[0]["payload"]["headline"] == "Review BTC first"


def test_assistant_context_cache_reuses_decision_context_reads():
    assistant_module._assistant_context_cache.clear()
    calls = {"score": 0, "setups": 0}

    class _ScoreRepo:
        async def get_master_score(self, user_id):
            calls["score"] += 1
            return SimpleNamespace(avg_score=83)

    class _SetupRepo:
        async def get_user_setups(self, user_id):
            calls["setups"] += 1
            return [SimpleNamespace(name="BTC Breakout")]

    service = AiAssistantService(
        score_repo=_ScoreRepo(),
        setup_repo=_SetupRepo(),
        report_repo=SimpleNamespace(),
        bot_repo=SimpleNamespace(),
        user_repo=SimpleNamespace(),
        market_data_repo=SimpleNamespace(),
        strategy_repo=SimpleNamespace(),
        state_repo=SimpleNamespace(),
        ai_gateway=SimpleNamespace(),
    )

    first = asyncio.run(service._build_context(11, "decision"))
    second = asyncio.run(service._build_context(11, "decision"))

    assert "CURRENT MASTER SCORE: 83" in first
    assert first == second
    assert calls == {"score": 1, "setups": 1}


def test_daily_report_preview_cache_reuses_generated_preview(monkeypatch):
    report_module._daily_report_preview_cache.clear()
    calls = {"count": 0}

    def fake_generate_daily_report_sections(*, user_id=None):
        calls["count"] += 1
        return {"headline": f"Daily preview for user {user_id}"}

    monkeypatch.setattr(report_module, "generate_daily_report_sections", fake_generate_daily_report_sections)

    service = ReportService(SimpleNamespace())
    first = asyncio.run(service.preview_daily_report(21))
    second = asyncio.run(service.preview_daily_report(21))

    assert calls["count"] == 1
    assert first == second
    assert first["report"]["headline"] == "Daily preview for user 21"
