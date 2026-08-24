from backend.services.finn_v2_evidence_validator_service import FinnV2EvidenceValidatorService


def test_stale_tool_artifact_uses_generic_freshness_provenance_code():
    service = FinnV2EvidenceValidatorService(session=object())

    assert service._stale_code("read_bot_status") == "evidence_freshness_stale:read_bot_status"
    assert service._stale_code("read_market_snapshot") == "evidence_freshness_stale:read_market_snapshot"
