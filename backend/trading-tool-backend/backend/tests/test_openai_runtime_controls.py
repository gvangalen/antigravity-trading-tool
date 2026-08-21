from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services.report_service import ReportService
from backend.services import ai_availability_service
from backend.utils import openai_client as openai_module


def test_openai_quota_breaker_short_circuits_json_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "true")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    ai_availability_service.reset_ai_availability_for_tests()
    openai_module._openai_runtime_state.update(
        {
            "quota_exhausted_until": 0.0,
            "quota_failures": 0,
            "blocked_calls": 0,
            "text_calls": 0,
            "json_calls": 0,
            "last_error": None,
            "last_error_at": None,
        }
    )
    monkeypatch.setattr(openai_module, "client", object())
    monkeypatch.setattr(openai_module, "api_key", "sk-test")
    monkeypatch.setattr(openai_module, "QUOTA_COOLDOWN_SECONDS", 600)

    openai_module._mark_quota_exhausted()
    result = openai_module.ask_gpt_json(prompt="{}", system_role="system")

    assert result["error"] == "ai_unavailable_budget"
    assert result["ai_status"]["available"] is False
    status = openai_module.get_openai_runtime_status()
    assert status["quota_breaker_active"] is True
    assert status["blocked_calls"] >= 1


def test_no_budget_mode_never_calls_openai(monkeypatch):
    class _Client:
        def with_options(self, **kwargs):
            raise AssertionError("OpenAI mag niet worden aangeroepen in no-budget mode")

    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "false")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    monkeypatch.setattr(openai_module, "client", _Client())
    monkeypatch.setattr(openai_module, "_log_openai_quota_skip", lambda reason: None)

    result = openai_module.ask_gpt_json(prompt="{}", system_role="system")

    assert result["error"] == "ai_unavailable_budget"
    assert result["ai_status"]["mode"] == "deterministic_only"


def test_block_observability_is_deduplicated(monkeypatch):
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    monkeypatch.setenv("OPENAI_BLOCK_LOG_WINDOW_SECONDS", "3600")
    ai_availability_service.reset_ai_availability_for_tests()

    assert ai_availability_service.should_emit_block_event("setup", "ai_unavailable_budget") is True
    assert ai_availability_service.should_emit_block_event("setup", "ai_unavailable_budget") is False
    assert ai_availability_service.should_emit_block_event("strategy", "ai_unavailable_budget") is True


def test_structured_response_exposes_incomplete_provider_details(monkeypatch):
    class _Incomplete:
        reason = "max_output_tokens"

    class _Content:
        type = "refusal"
        refusal = "I cannot comply"

    class _Output:
        content = [_Content()]

    class _Response:
        status = "incomplete"
        incomplete_details = _Incomplete()
        output = [_Output()]
        output_parsed = None

    class _Responses:
        @staticmethod
        def create(**_kwargs):
            return _Response()

    class _Client:
        responses = _Responses()

        def with_options(self, **_kwargs):
            return self

    monkeypatch.setattr(openai_module, "client", _Client())
    monkeypatch.setattr(openai_module, "get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(openai_module, "_rate_limit_allows_call", lambda: True)
    monkeypatch.setattr(openai_module, "_quota_breaker_active", lambda: False)

    result = openai_module.ask_gpt_structured_response(
        prompt="question",
        system_role="system",
        schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )

    assert result["error"] == "incomplete_structured_response"
    assert result["error_detail"] == {
        "response_status": "incomplete",
        "incomplete_reason": "max_output_tokens",
        "content_types": ["refusal"],
        "refusal": "I cannot comply",
        "json_parse_error": None,
        "request_id": None,
    }


def test_probe_openai_runtime_clears_breaker_after_success(monkeypatch):
    class _Parsed:
        model = "gpt-4o-mini"

    class _RawResponse:
        status_code = 200
        headers = {"x-request-id": "req_backend_probe"}

        @staticmethod
        def parse():
            return _Parsed()

    class _WithRawResponse:
        @staticmethod
        def create(**kwargs):
            return _RawResponse()

    class _Completions:
        with_raw_response = _WithRawResponse()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

        def with_options(self, **kwargs):
            return self

    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test-1234567890")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    monkeypatch.setattr(openai_module, "client", _Client())
    monkeypatch.setattr(openai_module, "api_key", "sk-proj-test-1234567890")
    ai_availability_service.reset_ai_availability_for_tests()
    ai_availability_service.mark_ai_unavailable("ai_unavailable_budget", 600)
    openai_module._openai_runtime_state["quota_exhausted_until"] = datetime.now().timestamp() + 600

    result = openai_module.probe_openai_runtime()

    assert result["ok"] is True
    assert result["request_id"] == "req_backend_probe"
    assert result["availability_before"]["available"] is False
    assert result["availability_after"]["available"] is True
    assert result["api_key_scope"] == "project_scoped"
    assert result["api_key_fingerprint"].startswith("sha256:")
    assert "sk-proj" not in result["api_key_fingerprint"]
    assert openai_module.get_openai_runtime_status()["quota_breaker_active"] is False


class _Repo:
    def __init__(self, latest_report):
        self.latest_report = latest_report

    async def get_latest_report(self, user_id, table_name, symbol=None):
        return self.latest_report


def test_generate_report_reuses_recent_daily_report_without_queueing_task(monkeypatch):
    now = datetime.utcnow()
    repository = _Repo(
        {
            "report_date": now.date(),
            "generated_at": now - timedelta(minutes=5),
        }
    )
    service = ReportService(repository)

    class _Task:
        id = "should-not-run"

    monkeypatch.setattr("backend.services.report_service.generate_daily_report", SimpleNamespace(delay=lambda **kwargs: _Task()))

    result = __import__("asyncio").run(service.generate_report(7, "daily"))

    assert result["source"] == "existing_daily_report"
    assert result["task_id"] is None
