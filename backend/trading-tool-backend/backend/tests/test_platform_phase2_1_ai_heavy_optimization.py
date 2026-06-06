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


def test_mission_control_explain_cache_reuses_response_and_invalidates(monkeypatch):
    finn_module._mission_control_preview_cache.clear()
    finn_module._mission_control_explain_cache.clear()
    service = FinnPlanService(None)
    calls = {"daily": 0, "governance": 0}

    async def fake_daily(user_id, query, context):
        calls["daily"] += 1
        return {
            "state": {
                "analysis": {
                    "portfolio_risk": {"status": "watch", "message": "BTC review"},
                    "blocked_assets": [],
                    "warning_assets": [],
                    "reasons": [],
                    "suggested_actions": [],
                }
            }
        }

    async def fake_governance(user_id, *, event_types, limit=40):
        calls["governance"] += 1
        return []

    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", fake_daily)
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {"summary": {"open_action_count": 2}})
    monkeypatch.setattr(service, "_fetch_recent_governance_events", fake_governance)
    monkeypatch.setattr(service, "_priority_engine_payload", lambda mission, analysis, signals: {
        "headline": "Vandaag eerst BTC reviewen.",
        "top_priorities": [{"title": "BTC review", "type": "review", "priority": "high", "why_now": "hoge exposure", "asset": "BTC"}],
        "ignore_today": [],
        "open_counts": {"workqueue_count": 2, "high_priority_count": 1},
    })
    monkeypatch.setattr(service, "_priority_engine_governance_signals", lambda events: {})

    first = asyncio.run(service.build_mission_control_explain_response(5, "Vat Mission Control samen in drie bullets", {"page": "dashboard"}))
    second = asyncio.run(service.build_mission_control_explain_response(5, "Vat Mission Control samen in drie bullets", {"page": "dashboard"}))

    assert calls == {"daily": 1, "governance": 1}
    assert first == second

    FinnPlanService.invalidate_runtime_caches_for_user(5)
    asyncio.run(service.build_mission_control_explain_response(5, "Vat Mission Control samen in drie bullets", {"page": "dashboard"}))

    assert calls == {"daily": 2, "governance": 2}


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


def test_daily_report_preview_prefers_todays_existing_report(monkeypatch):
    report_module._daily_report_preview_cache.clear()

    class _Repo:
        async def get_latest_report(self, user_id, table_name, symbol=None):
            from datetime import datetime

            return {
                "report_date": datetime.utcnow().date(),
                "summary": "Daily summary ready",
                "market_analysis": "Market calm",
                "outlook": "Wait for confirmation",
                "macro_score": 50.0,
                "technical_score": 40.0,
                "market_score": 35.0,
                "setup_score": 72.0,
            }

    def fail_generate(*args, **kwargs):
        raise AssertionError("generator should not run when today's report exists")

    monkeypatch.setattr(report_module, "generate_daily_report_sections", fail_generate)

    service = ReportService(_Repo())
    preview = asyncio.run(service.preview_daily_report(33))

    assert preview["source"] == "latest_daily_report"
    assert preview["report"]["executive_summary"] == "Daily summary ready"
    assert preview["report"]["market_analysis"] == "Market calm"


def test_dashboard_context_query_routes_to_page_explain():
    service = FinnPlanService(None)

    assert service.looks_like_entity_explain_request("Leg mijn huidige dashboardcontext kort uit.", {}) is True
    assert service._context_explain_target("Leg mijn huidige dashboardcontext kort uit.", {}) == "page"

    result = asyncio.run(service.build_context_explain_response(1, "Leg mijn huidige dashboardcontext kort uit.", {}))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "page"
    assert "dashboard" in result["response"].lower()
