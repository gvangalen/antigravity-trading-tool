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
    service.record_event(
        user_id=7,
        event={
            "event_name": "screen_view",
            "session_id": "sess-c",
            "surface": "web",
            "page": "/onboarding",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "onboarding_step_clicked",
            "session_id": "sess-c",
            "surface": "web",
            "page": "/onboarding",
            "action_type": "market",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "onboarding_step_completed",
            "session_id": "sess-c",
            "surface": "web",
            "page": "/market",
            "action_type": "market",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "onboarding_completed",
            "session_id": "sess-c",
            "surface": "web",
            "page": "/onboarding",
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "onboarding_dashboard_activated",
            "session_id": "sess-c",
            "surface": "web",
            "page": "/onboarding",
            "action_type": "activate_dashboard",
        },
    )

    snapshot = service.snapshot()

    assert snapshot["event_counts"]["screen_view"] == 2
    assert snapshot["top_prompts"][0]["prompt"] == "Beoordeel deze setup voor BTC"
    assert snapshot["top_screens"][0]["page"] == "/setup"
    assert snapshot["top_first_screens"][0]["page"] == "/setup"
    assert snapshot["confirm_funnel"] == {"opened": 1, "confirmed": 1, "canceled": 0}
    assert snapshot["onboarding_funnel"] == {
        "sessions_seen": 1,
        "step_clicked": 1,
        "step_completed": 1,
        "completed": 1,
        "dashboard_activated": 1,
    }
    assert snapshot["first_session_summary"]["sessions_seen"] == 2
    assert snapshot["first_session_summary"]["sessions_with_prompt"] == 1
    assert snapshot["first_session_summary"]["sessions_with_confirm"] == 1
    assert snapshot["top_cta_actions"][0]["action"] in {"market", "activate_dashboard"}
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


def test_decision_review_classifier_catches_setup_strategy_fit_prompt():
    service = FinnPlanService(None)

    assert service.looks_like_decision_review_request(
        "Past deze setup nu bij mijn strategie?",
        {"page": "setup", "page_type": "Setup", "setup_id": 12, "symbol": "BTC"},
    )
    assert not service.looks_like_daily_coach_request("Past deze setup nu bij mijn strategie?")


def test_decision_review_classifier_catches_short_trade_intent_prompt():
    service = FinnPlanService(None)

    assert service.looks_like_decision_review_request(
        "Zou jij dit nu openen?",
        {"page": "setup", "page_type": "Setup", "setup_id": 12, "symbol": "BTC"},
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "Past deze trade bij mijn plan?",
        "Klopt deze setup met mijn aanpak?",
        "Is dit slim binnen mijn strategie?",
        "Zou jij deze entry nu nemen?",
    ],
)
def test_decision_review_classifier_catches_implicit_variant_prompts(prompt: str):
    service = FinnPlanService(None)

    assert service.looks_like_decision_review_request(
        prompt,
        {"page": "setup", "page_type": "Setup", "setup_id": 12, "strategy_id": 3, "symbol": "BTC"},
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "Is deze te doen?",
        "Voelt dit goed genoeg?",
        "Zou jij hier instappen?",
        "Is dit nog oké?",
        "Is deze entry het waard?",
    ],
)
def test_decision_review_classifier_catches_indirect_boundary_prompts(prompt: str):
    service = FinnPlanService(None)

    assert service.looks_like_decision_review_request(
        prompt,
        {"page": "setup", "page_type": "Setup", "setup_id": 12, "strategy_id": 3, "symbol": "BTC"},
    )


def test_ultra_implicit_prompt_policy_routes_to_decision_review_with_context():
    service = FinnPlanService(None)

    assert service.looks_like_ultra_implicit_review_prompt("Doe ik dit goed?")
    assert service.should_route_ultra_implicit_prompt_to_decision_review(
        "Doe ik dit goed?",
        {"page": "setup", "page_type": "Setup", "setup_id": 12, "symbol": "BTC"},
    )


def test_ultra_implicit_prompt_policy_stays_fast_help_without_context():
    service = FinnPlanService(None)

    assert service.looks_like_ultra_implicit_review_prompt("Hmm, en deze dan?")
    assert not service.should_route_ultra_implicit_prompt_to_decision_review(
        "Hmm, en deze dan?",
        {"page": None, "page_type": None},
    )

    payload = asyncio.run(service.build_quick_general_help_response(
        7,
        "Hmm, en deze dan?",
        {"page": None, "page_type": None},
    ))

    assert payload["intent"] == "general_help"
    assert payload["analysis"]["route_source"] == "finn_fast_help"
    assert payload["summary"]
    assert payload["next_best_action"]
