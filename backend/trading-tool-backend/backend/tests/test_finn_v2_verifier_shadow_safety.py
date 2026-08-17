from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verifier_shadow_path_keeps_internal_delivery_and_no_public_route():
    service_source = (ROOT / "services" / "finn_v2_response_verifier_service.py").read_text(encoding="utf-8")
    delivery_source = (ROOT / "services" / "finn_v2_delivery_service.py").read_text(encoding="utf-8")
    api_source = (ROOT / "api" / "ai_assistant_api.py").read_text(encoding="utf-8")

    assert "FinnV2DeliveryEnvelope" in service_source
    assert "run.completed" in delivery_source
    assert "finn_v2_verified" not in api_source
