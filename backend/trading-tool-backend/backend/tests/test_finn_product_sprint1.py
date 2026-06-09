from backend.api.ai_assistant_api import _normalize_finn_response_contract
from backend.services.finn_product_analytics_service import FinnProductAnalyticsService
from backend.services.finn_plan_service import FinnPlanService
import asyncio
import pytest


def test_normalize_finn_response_contract_promotes_primary_fields():
    payload = _normalize_finn_response_contract(
        {
            "response": "Finn kan dit verder uitleggen.",
            "analysis": {
                "summary": "Korte conclusie",
                "risk_summary": "Risico blijft beheersbaar.",
                "next_best_actions": [{"label": "Review setup opnieuw"}],
                "review_reason": "De setup wijkt af van je plan.",
            },
        }
    )

    assert payload["summary"] == "Korte conclusie"
    assert payload["risk_summary"] == "Risico blijft beheersbaar."
    assert payload["next_best_action"] == "Review setup opnieuw"
    assert payload["review_reason"] == "De setup wijkt af van je plan."


def test_normalize_finn_response_contract_uses_response_as_summary_fallback():
    payload = _normalize_finn_response_contract({"response": "Dit is de hoofduitleg."})

    assert payload["summary"] == "Dit is de hoofduitleg."
    assert payload["risk_summary"] is None
    assert payload["next_best_action"] is None


def test_finn_product_analytics_snapshot_counts_prompts_screens_and_funnel():
    service = FinnProductAnalyticsService(max_events=20, screen_dedupe_seconds=30)

    service.record_event(
        user_id=7,
        event={
            "event_name": "finn_prompt_submitted",
            "prompt_text": "Beoordeel deze setup voor BTC",
            "session_id": "sess-a",
            "surface": "web",
            "page": "/setup",
            "flow_type": "setup_review",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "screen_view",
            "session_id": "sess-a",
            "surface": "web",
            "page": "/setup",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "screen_view",
            "session_id": "sess-a",
            "surface": "web",
            "page": "/setup",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "finn_confirm_opened",
            "session_id": "sess-a",
            "surface": "web",
            "page": "/setup",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "finn_confirm_confirmed",
            "session_id": "sess-a",
            "surface": "web",
            "page": "/setup",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "decision_review_used",
            "session_id": "sess-b",
            "surface": "web",
            "page": "/setup",
            "flow_type": "decision_review",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "priority_engine_used",
            "session_id": "sess-b",
            "surface": "web",
            "page": "/portfolio",
            "flow_type": "priority_engine",
        },
    )

    snapshot = service.snapshot()

    assert snapshot["event_counts"]["screen_view"] == 1
    assert snapshot["top_prompts"][0]["prompt"] == "Beoordeel deze setup voor BTC"
    assert snapshot["top_screens"][0]["page"] == "/setup"
    assert snapshot["confirm_funnel"] == {"opened": 1, "confirmed": 1, "canceled": 0}
    assert snapshot["decision_review_usage_count"] == 1
    assert snapshot["priority_engine_usage_count"] == 1
    assert snapshot["repeated_user_signal"]["users_with_multiple_sessions"] == 1


def test_general_capability_response_carries_operator_contract():
    service = FinnPlanService(None)

    payload = asyncio.run(service.build_general_capability_response(
        7,
        "Wat kan Finn hier doen?",
        {"page": "setup", "page_type": "Setup", "symbol": "BTC"},
    ))

    assert payload["summary"]
    assert payload["risk_summary"]
    assert payload["next_best_action"]
    assert payload["review_reason"]
    assert payload["analysis"]["summary"] == payload["summary"]
    assert payload["analysis"]["operator_resolution"]["summary"] == payload["review_reason"]


def test_decision_review_response_carries_operator_summary_and_next_step():
    service = FinnPlanService(None)

    payload = asyncio.run(service.build_decision_review_response(
        7,
        "Beoordeel deze trade voor BTC met 3% risico",
        {"page": "setup", "page_type": "Setup", "symbol": "BTC"},
    ))

    assert payload["intent"] == "decision_review"
    assert payload["summary"]
    assert payload["risk_summary"]
    assert payload["next_best_action"]
    assert payload["review_reason"]
    assert payload["analysis"]["summary"] == payload["summary"]
    assert payload["analysis"]["next_best_action"] == payload["next_best_action"]
    assert payload["analysis"]["operator_resolution"]["what_next"][0] == payload["next_best_action"]


def test_plan_adherence_response_carries_operator_summary_and_recovery():
    service = FinnPlanService(None)

    payload = asyncio.run(service.build_plan_adherence_review_response(
        7,
        "Mijn plan zegt wachten maar ik wil toch kopen",
        {"page": "setup", "page_type": "Setup", "symbol": "BTC"},
    ))

    assert payload["intent"] == "plan_adherence_review"
    assert payload["summary"]
    assert payload["risk_summary"]
    assert payload["next_best_action"]
    assert payload["review_reason"]
    assert payload["analysis"]["summary"] == payload["summary"]
    assert payload["analysis"]["operator_resolution"]["summary"] == payload["review_reason"]
