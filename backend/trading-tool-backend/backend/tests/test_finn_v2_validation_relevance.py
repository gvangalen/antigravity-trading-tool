from backend.schemas.finn_v2_domain_validation_schema import EvidenceIssue
from backend.schemas.finn_v2_state_schema import ToolOutcome
from backend.services.finn_v2_evidence_validator_service import FinnV2EvidenceValidatorService


def _outcomes(**rows):
    return {key: ToolOutcome(tool_name=key, status=value, artifact_id=f"{key}-artifact") for key, value in rows.items()}


def test_relevance_rules_keep_unrelated_domains_available():
    service = FinnV2EvidenceValidatorService(session=object())

    identity = service._domain_status("identity_context", ["read_profile", "read_user_preferences", "read_active_asset"], _outcomes(read_profile="available", read_user_preferences="available", read_active_asset="unavailable"), [])
    market = service._domain_status("market_context", ["read_active_asset", "read_indicator_configuration", "read_asset_scores", "read_market_snapshot"], _outcomes(read_active_asset="available", read_indicator_configuration="available", read_asset_scores="unavailable", read_market_snapshot="stale"), [EvidenceIssue(code="score_missing", severity="warning", domain="market_context", message="x")])
    plan = service._domain_status("plan_context", ["read_active_asset", "read_indicator_configuration", "read_active_setup", "read_linked_strategy"], _outcomes(read_active_asset="available", read_indicator_configuration="unavailable", read_active_setup="available", read_linked_strategy="available"), [])
    automation = service._domain_status("automation_context", ["read_active_setup", "read_linked_strategy", "read_linked_bot", "read_bot_status"], _outcomes(read_active_setup="available", read_linked_strategy="available", read_linked_bot="available", read_bot_status="stale"), [])
    review = service._domain_status("review_context", ["read_review_history"], _outcomes(read_review_history="unavailable"), [])

    assert identity == "degraded"
    assert market == "degraded"
    assert plan in {"degraded", "available"}
    assert automation == "degraded"
    assert review == "unavailable"

