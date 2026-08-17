from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_policy_and_proposal_repositories_are_owner_scoped():
    policy_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_policy_repository.py").read_text(encoding="utf-8")
    proposal_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_proposal_repository.py").read_text(encoding="utf-8")
    confirmation_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_confirmation_repository.py").read_text(encoding="utf-8")
    eligibility_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_eligibility_repository.py").read_text(encoding="utf-8")

    assert "FinnV2PolicyDecisionModel.user_id == user_id" in policy_source
    assert "FinnV2Proposal.user_id == user_id" in proposal_source
    assert "FinnV2Confirmation.user_id == user_id" in confirmation_source
    assert "FinnV2EligibilityDecision.user_id == user_id" in eligibility_source
