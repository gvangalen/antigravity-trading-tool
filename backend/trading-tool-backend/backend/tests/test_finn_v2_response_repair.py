from datetime import datetime, timezone

from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.services.finn_v2_response_repair_service import FinnV2ResponseRepairService


def test_response_repair_adds_uncertainty_and_removes_invalid_follow_up():
    service = FinnV2ResponseRepairService()
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="READ",
        direct_answer="De context is goed.",
        main_observation="Er is weinig risico.",
        follow_up_question="Wil je meer weten?",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )

    repaired = service.repair(
        draft=draft,
        reason_codes=["missing_uncertainty", "follow_up_invalid"],
        uncertainty_summary="De botstatus is verouderd.",
    )

    assert repaired.uncertainty_summary == "De botstatus is verouderd."
    assert repaired.follow_up_question is None


def test_evaluate_repair_restores_a_safe_concrete_next_step():
    draft = ResponseDraft(
        draft_id="draft-2", run_id="run-2", user_id=7, mode="EVALUATE",
        direct_answer="De huidige onderbouwing is beperkt.",
        main_observation="De setupgegevens zijn ouder dan de overige evidence.",
        evidence_set_hash="hash-2", created_at=datetime.now(timezone.utc),
    )

    repaired = FinnV2ResponseRepairService().repair(
        draft=draft, reason_codes=["response_field_incomplete"], uncertainty_summary=None,
    )

    assert repaired.next_step
    assert "gegevens" in repaired.next_step.instruction


def test_unsupported_noncritical_claim_repair_drops_material_claims_even_with_refs():
    draft = ResponseDraft(
        draft_id="draft-3", run_id="run-3", user_id=7, mode="EVALUATE",
        direct_answer="RSI staat op 57,4.", main_observation="De marktbron ontbreekt.",
        claims=[
            ResponseClaim(claim_id="C1", claim_type="evaluation", text="RSI bewijst dat het plan past.", evidence_refs=["E1"], confidence="medium"),
            ResponseClaim(claim_id="C2", claim_type="uncertainty", text="De marktbron is niet beschikbaar.", evidence_refs=["E2"], confidence="high"),
        ],
        evidence_set_hash="hash-3", created_at=datetime.now(timezone.utc),
    )

    repaired = FinnV2ResponseRepairService().repair(
        draft=draft, reason_codes=["unsupported_noncritical_claim"], uncertainty_summary=None,
        rejected_claim_ids={"C1"},
    )

    assert [claim.claim_id for claim in repaired.claims] == ["C2"]


def test_configuration_causality_repair_keeps_grounded_claims_and_rebuilds_prose():
    draft = ResponseDraft(
        draft_id="draft-4", run_id="run-4", user_id=7, mode="EVALUATE",
        direct_answer="RSI veroorzaakt een betere entry.",
        main_observation="RSI staat op 57,4 en de marktbron ontbreekt.",
        claims=[
            ResponseClaim(claim_id="C1", claim_type="evaluation", text="RSI veroorzaakt een betere entry.", evidence_refs=["E1"], confidence="medium"),
            ResponseClaim(claim_id="C2", claim_type="fact", text="RSI staat op 57,4.", evidence_refs=["E1"], confidence="high"),
            ResponseClaim(claim_id="C3", claim_type="uncertainty", text="Een actuele marktbron ontbreekt.", evidence_refs=["E2"], confidence="high"),
        ],
        evidence_set_hash="hash-4", created_at=datetime.now(timezone.utc),
    )

    repaired = FinnV2ResponseRepairService().repair(
        draft=draft,
        reason_codes=["unsupported_configuration_causality"],
        uncertainty_summary=None,
        rejected_claim_ids={"C1"},
    )

    assert [claim.claim_id for claim in repaired.claims] == ["C2", "C3"]
    assert repaired.direct_answer == "RSI staat op 57,4."
    assert repaired.main_observation == "Een actuele marktbron ontbreekt."


def test_evaluate_repair_projects_existing_uncertainty_as_typed_claim():
    draft = ResponseDraft(
        draft_id="draft-5", run_id="run-5", user_id=7, mode="EVALUATE",
        direct_answer="RSI geeft een gegarandeerde entry.",
        main_observation="RSI staat op 64.",
        claims=[
            ResponseClaim(claim_id="C1", claim_type="evaluation", text="RSI geeft een gegarandeerde entry.", evidence_refs=["E1"], confidence="medium"),
            ResponseClaim(claim_id="C2", claim_type="fact", text="RSI staat op 64.", evidence_refs=["E1"], confidence="high"),
        ],
        evidence_refs_used=["E1", "E2"],
        uncertainty_summary="De bredere marktcontext is niet beschikbaar.",
        evidence_set_hash="hash-5", created_at=datetime.now(timezone.utc),
    )

    repaired = FinnV2ResponseRepairService().repair(
        draft=draft,
        reason_codes=["unsupported_noncritical_claim"],
        uncertainty_summary=None,
        rejected_claim_ids={"C1"},
    )

    assert [claim.claim_type for claim in repaired.claims] == ["fact", "uncertainty"]
    assert repaired.claims[-1].evidence_refs == ["E1", "E2"]
