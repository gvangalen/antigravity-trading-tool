from backend.utils import openai_client as openai_module
from backend.services import ai_availability_service


class _ParsedContent:
    def __init__(self, parsed):
        self.parsed = parsed


class _OutputItem:
    def __init__(self, parsed):
        self.content = [_ParsedContent(parsed)]


class _Response:
    def __init__(self, parsed):
        self.output = [_OutputItem(parsed)]
        self.usage = type("Usage", (), {"input_tokens": 11, "output_tokens": 22, "reasoning_tokens": 3})()
        self.model = "gpt-4o-mini"


class _ResponsesClient:
    def create(self, **_kwargs):
        return _Response(
            {
                "mode": "FACT",
                "direct_answer": "Je actieve setup is BTC Swing.",
                "main_observation": "De actieve setup is duidelijk gekoppeld aan BTC.",
                "supporting_points": [],
                "claims": [{"claim_id": "C1", "claim_type": "fact", "text": "BTC Swing is actief.", "evidence_refs": ["E1"], "confidence": "high"}],
                "uncertainty_summary": None,
                "uncertainty_codes": [],
                "next_step": None,
                "follow_up_question": None,
                "proposal_candidate": None,
                "evidence_refs_used": ["E1"],
            }
        )


class _Client:
    def with_options(self, **_kwargs):
        return self

    @property
    def responses(self):
        return _ResponsesClient()


class _OutputTextResponse:
    status = "completed"
    output = []
    usage = type("Usage", (), {"input_tokens": 11, "output_tokens": 22, "reasoning_tokens": 3})()
    model = "gpt-4o-mini"

    def __init__(self, output_text):
        self.output_text = output_text


class _OutputTextResponsesClient:
    def create(self, **_kwargs):
        return _OutputTextResponse(
            '{"mode":"READ","direct_answer":"BTC is active.","main_observation":"The active setup is scoped to BTC.","supporting_points":[],"claims":[],"uncertainty_summary":null,"uncertainty_codes":[],"next_step":null,"follow_up_question":null,"proposal_candidate":null,"evidence_refs_used":["E1"]}'
        )


class _OutputTextClient(_Client):
    @property
    def responses(self):
        return _OutputTextResponsesClient()


def test_central_structured_response_path_uses_parsed_output_only(monkeypatch):
    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    ai_availability_service.reset_ai_availability_for_tests()
    monkeypatch.setattr(openai_module, "client", _Client())
    monkeypatch.setattr(openai_module, "api_key", "sk-test")

    result = openai_module.ask_gpt_structured_response(
        prompt="prompt",
        system_role="system",
        schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )

    assert result["parsed"]["mode"] == "FACT"
    assert result["input_tokens"] == 11


def test_central_structured_response_path_parses_completed_output_text(monkeypatch):
    monkeypatch.setenv("OPENAI_CALLS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai_availability_service, "_redis_client", lambda: None)
    ai_availability_service.reset_ai_availability_for_tests()
    monkeypatch.setattr(openai_module, "client", _OutputTextClient())
    monkeypatch.setattr(openai_module, "api_key", "sk-test")

    result = openai_module.ask_gpt_structured_response(
        prompt="prompt",
        system_role="system",
        schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    )

    assert result["parsed"]["mode"] == "READ"
    assert result["provider_metadata"]["response_status"] == "completed"
    assert result["provider_metadata"]["parsed_source"] == "response_output_text"
