from backend.services.finn_product_analytics_service import FinnProductAnalyticsService
import asyncio
import pytest


def test_response_trace_lookup_is_user_scoped_and_uses_memory_fallback(monkeypatch):
    monkeypatch.setattr(
        "backend.services.finn_product_analytics_service.fetch_finn_response_trace",
        lambda **kwargs: None,
    )
    service = FinnProductAnalyticsService(max_events=10)
    service.record_event(
        user_id=7,
        event={
            "event_name": "finn_response_trace",
            "trace_id": "trace-private",
            "metadata": {"trace_id": "trace-private", "decision": {"response_source": "database"}},
        },
    )

    assert service.get_response_trace(user_id=7, trace_id="trace-private")["trace_id"] == "trace-private"
    assert service.get_response_trace(user_id=8, trace_id="trace-private") is None
    assert service.get_response_trace(user_id=7, trace_id="missing") is None


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
            "event_name": "behavioral_intervention_seen",
            "session_id": "sess-b",
            "surface": "report_governance",
            "page": "/report",
            "flow_type": "behavioral_intervention",
            "metadata": {
                "behavior_flag": "fomo",
                "behavior_label": "FOMO",
            },
        },
    )
    service.record_event(
        user_id=7,
        event={
            "event_name": "behavioral_intervention_acknowledged",
            "session_id": "sess-b",
            "surface": "live_preflight",
            "page": "/bot",
            "flow_type": "behavioral_intervention",
            "metadata": {
                "behavior_flag": "fomo",
                "behavior_label": "FOMO",
            },
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
    assert snapshot["behavioral_intervention_seen_count"] == 1
    assert snapshot["behavioral_intervention_ack_count"] == 1
    assert snapshot["top_behavioral_flags"][0] == {"flag": "fomo", "count": 2}
    assert snapshot["top_behavioral_surfaces"][0]["surface"] in {"report_governance", "live_preflight"}
    assert snapshot["repeated_user_signal"]["users_with_multiple_sessions"] == 1


def test_finn_product_analytics_persists_normalized_events(monkeypatch):
    service = FinnProductAnalyticsService(max_events=5, screen_dedupe_seconds=30)
    captured = []

    monkeypatch.setattr(service, "_persist_event", lambda event: captured.append(event))

    service.record_event(
        user_id=11,
        event={
            "event_name": "finn_prompt_submitted",
            "prompt_text": "  Beoordeel   deze setup   voor BTC  ",
            "session_id": "sess-persist",
            "surface": "web",
            "page": "/setup",
            "flow_type": "decision_review",
        },
    )

    assert len(captured) == 1
    assert captured[0]["prompt_text"] == "Beoordeel deze setup voor BTC"
    assert captured[0]["user_id"] == 11
    assert captured[0]["page"] == "/setup"
    assert captured[0]["timestamp"] is not None


def test_finn_product_analytics_snapshot_prefers_persistent_store(monkeypatch):
    service = FinnProductAnalyticsService(max_events=5, screen_dedupe_seconds=30)

    monkeypatch.setattr(service, "_persistent_snapshot", lambda: {"metrics_scope": "persistent_store", "event_count": 9})

    snapshot = service.snapshot()

    assert snapshot["metrics_scope"] == "persistent_store"
    assert snapshot["event_count"] == 9
