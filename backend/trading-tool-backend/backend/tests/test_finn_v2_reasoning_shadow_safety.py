from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reasoning_shadow_path_uses_central_client_and_no_tool_loop():
    service_source = (ROOT / "services" / "finn_v2_reasoning_service.py").read_text(encoding="utf-8")
    client_source = (ROOT / "utils" / "openai_client.py").read_text(encoding="utf-8")

    assert "ask_gpt_structured_response" in service_source
    assert "tools" not in client_source.lower().split("ask_gpt_structured_response", 1)[1][:500]
    assert "responses.create" in client_source
