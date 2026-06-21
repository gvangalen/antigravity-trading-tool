from backend.services.ai_usage_observability_service import (
    ai_usage_context,
    classify_request_source,
    get_ai_usage_context,
    infer_entry_point,
)


def test_classify_request_source_separates_live_staging_qa_and_background():
    assert classify_request_source(
        user_email="gerrit@tradamind.com",
        app_env="production",
        run_kind="interactive",
    ) == "live_user"
    assert classify_request_source(
        user_email="staging.operator@example.com",
        app_env="staging",
        run_kind="interactive",
    ) == "qa_user"
    assert classify_request_source(
        user_email="henk@tradamind.com",
        app_env="staging",
        run_kind="interactive",
    ) == "staging_user"
    assert classify_request_source(
        user_email="henk@tradamind.com",
        app_env="production",
        run_kind="scheduled",
    ) == "background_job"


def test_ai_usage_context_scopes_and_resets():
    assert get_ai_usage_context() is None

    with ai_usage_context(user_id=7, purpose="daily_report_generation", request_source="background_job"):
        context = get_ai_usage_context()
        assert context is not None
        assert context["user_id"] == 7
        assert context["purpose"] == "daily_report_generation"
        assert context["request_source"] == "background_job"

    assert get_ai_usage_context() is None


def test_infer_entry_point_maps_report_and_chat_families():
    assert infer_entry_point(purpose="daily_report_generation", run_kind="scheduled") == "daily_report_task"
    assert infer_entry_point(purpose="daily_report_preview", run_kind="interactive") == "report_service:daily_preview"
    assert infer_entry_point(purpose="chat_general", run_kind="interactive") == "assistant_service:general"
    assert infer_entry_point(purpose="decision_review", run_kind="interactive") == "assistant_service:decision_review"
