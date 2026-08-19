from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate
from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def test_scope_coverage_fails_when_a1_reduces_to_indicator_only():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="EVALUATION",
        direct_answer="Je RSI staat goed.",
        main_observation="De indicatoren ogen sterk.",
        claims=[ResponseClaim(claim_id="C1", claim_type="evaluation", text="RSI is sterk.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-1", user_id=7, message="Beoordeel profiel, indicators, setup, strategy en bot", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-1", evidence_set_hash="hash-1", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is False
    assert "response_scope_incomplete" in verifier.reason_codes


def test_scope_coverage_allows_setup_proposal_when_identity_context_is_sufficient():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-setup-proposal",
        run_id="run-setup-proposal",
        user_id=7,
        mode="CREATE_PROPOSAL",
        direct_answer="Ik kan een concept-setup voor BTC voorbereiden met 4H als primair timeframe.",
        main_observation="Deze setup is nog niet opgeslagen; het gaat om een voorstel dat eerst bevestigd moet worden.",
        claims=[],
        proposal_candidate=ProposalCandidate(
            operation_type="create_setup",
            target_type="setup",
            target_id=None,
            asset="BTC",
            proposed_changes={"setup_fields": {"symbol": "BTC", "timeframe": "4H"}},
            evidence_refs=["E1"],
            impact_summary="Er wordt een nieuwe BTC-setup voorbereid na bevestiging.",
            risk_summary="De setup wordt pas opgeslagen na bevestiging.",
            confirmation_required=True,
        ),
        evidence_set_hash="hash-setup",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-setup-proposal", user_id=7, message="Maak een setup voor BTC swing trading met daily trend en 4H entry.", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["setup"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=True, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_active_asset", entity_type="asset", entity_id="BTC", asset="BTC", freshness="fresh", confidence="high", facts={"symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-setup", evidence_set_hash="hash-setup", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is True
    assert "response_scope_incomplete" not in verifier.reason_codes


def test_mode_purity_accepts_not_executed_watchlist_proposal_wording():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-watchlist-proposal",
        run_id="run-watchlist-proposal",
        user_id=7,
        mode="ACTION_PROPOSAL",
        direct_answer="Ik kan ETH aan je watchlist toevoegen na je bevestiging.",
        main_observation="De wijziging is nog niet uitgevoerd; ik heb alleen een voorstel voor ETH voorbereid.",
        claims=[],
        evidence_set_hash="hash-watch",
        created_at=datetime.now(timezone.utc),
    )

    assert service._mode_purity_ok(draft) is True
