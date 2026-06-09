from backend.api.ai_assistant_api import _normalize_finn_response_contract
from backend.services.finn_product_analytics_service import FinnProductAnalyticsService


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
