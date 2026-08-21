from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningNextStep
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
        force_action="deliver",
    )

    assert verifier.coverage.coverage_ok is False
    assert verifier.passed is False
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


def test_scope_coverage_uses_top_level_model_evidence_references():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-model-refs",
        run_id="run-model-refs",
        user_id=7,
        mode="EVALUATE",
        direct_answer="Je BTC-plan bevat setup 293, strategie 309 en bot 170.",
        main_observation="Je swing_trader-profiel gebruikt RSI en volume voor BTC.",
        claims=[],
        evidence_refs_used=["E1", "E2", "E3", "E4", "E5"],
        next_step=ReasoningNextStep(
            title="Leg je beslisregel vast",
            instruction="Leg vast wanneer RSI en volume samen je BTC-setup bevestigen.",
            operation_type=None,
            target_entity_type="setup",
            target_entity_id="293",
            requires_confirmation=False,
        ),
        evidence_set_hash="hash-model-refs",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_profile", entity_type="profile", entity_id="7", asset=None, freshness="fresh", confidence="high", facts={"trader_profile": {"trader_types": ["swing_trader"]}}),
        SimpleNamespace(evidence_id="E2", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]}),
        SimpleNamespace(evidence_id="E3", domain="plan_context", tool_name="read_active_setup", entity_type="setup", entity_id="293", asset="BTC", freshness="fresh", confidence="high", facts={"setup_id": 293}),
        SimpleNamespace(evidence_id="E4", domain="plan_context", tool_name="read_linked_strategy", entity_type="strategy", entity_id="309", asset="BTC", freshness="fresh", confidence="high", facts={"strategy_id": 309}),
        SimpleNamespace(evidence_id="E5", domain="automation_context", tool_name="read_linked_bot", entity_type="bot", entity_id="170", asset="BTC", freshness="fresh", confidence="high", facts={"bot_id": 170}),
    ]

    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-model-refs", user_id=7, message="Bekijk mijn profiel, indicatoren, setup, strategie en gekoppelde bot. Geef een observatie en vervolgstap.", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-model-refs", evidence_set_hash="hash-model-refs", integrity_status="valid"),
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


def test_mode_purity_allows_read_response_to_reference_stored_order_reasoning():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-bot-read",
        run_id="run-bot-read",
        user_id=7,
        mode="READ",
        direct_answer="Wat ik zeker weet: bot 170 is gekoppeld, actief en niet live.",
        main_observation="Wat ik nog niet bevestigd kan afleiden: deze evidence bevat geen opgeslagen order- of positiereden die exact verklaart waarom nog geen positie is geopend.",
        claims=[],
        evidence_set_hash="hash-bot-read",
        created_at=datetime.now(timezone.utc),
    )

    assert service._mode_purity_ok(draft) is True


def test_blocked_live_bot_unavailable_is_not_marked_as_paper_live_mismatch():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-live-blocked",
        run_id="run-live-blocked",
        user_id=7,
        mode="UNAVAILABLE",
        direct_answer="Ik kan deze bot niet live activeren.",
        main_observation="De live-activatie blijft geblokkeerd door de actieve safety- en policycontroles.",
        claims=[],
        evidence_set_hash="hash-live-blocked",
        created_at=datetime.now(timezone.utc),
    )

    assert service._paper_live_mismatch(
        draft,
        {
            "E1": SimpleNamespace(facts={"is_live": False}),
        },
    ) is False


def test_read_response_marks_strategy_scope_from_linked_strategy_evidence():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-strategy-read",
        run_id="run-strategy-read",
        user_id=7,
        mode="READ",
        direct_answer="De belangrijkste expliciet opgeslagen entryvoorwaarde in je BTC-strategie 309 is nu een limit entry rond 62000.",
        main_observation="Wat nog niet bevestigd kan worden, is een extra entryfilter voor BTC.",
        claims=[
            ResponseClaim(
                claim_id="strategy-status",
                claim_type="fact",
                text="Strategie 309 voor setup 293 gebruikt execution_mode fixed.",
                evidence_refs=["E1"],
                confidence="high",
            )
        ],
        evidence_set_hash="hash-strategy-read",
        created_at=datetime.now(timezone.utc),
    )

    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-strategy-read", user_id=7, message="Welke belangrijkste entryvoorwaarde uit mijn BTC-strategie moet bevestigd zijn voordat mijn plan een entry toestaat?", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["strategy"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="plan_context", tool_name="read_linked_strategy", entity_type="strategy", entity_id="309", asset="BTC", freshness="fresh", confidence="high", facts={"strategy_id": 309, "symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-strategy-read", evidence_set_hash="hash-strategy-read", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is True
    assert verifier.relevance_ok is True
    assert "response_scope_incomplete" not in verifier.reason_codes
    assert "response_not_answering_question" not in verifier.reason_codes


def test_not_live_read_response_is_not_marked_as_live_mismatch():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-not-live-read",
        run_id="run-not-live-read",
        user_id=7,
        mode="READ",
        direct_answer="Wat ik zeker weet over je BTC-bot: bot 170 is gekoppeld, actief en niet live.",
        main_observation="Wat ik nog niet bevestigd kan worden, is waarom nog geen positie is geopend.",
        claims=[],
        evidence_set_hash="hash-not-live-read",
        created_at=datetime.now(timezone.utc),
    )

    assert service._paper_live_mismatch(
        draft,
        {
            "E1": SimpleNamespace(facts={"is_live": False}),
        },
    ) is False


def test_gate5_evaluation_rejects_generic_response_when_profile_and_indicator_grounding_exist():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-gate5-generic",
        run_id="run-gate5-generic",
        user_id=7,
        mode="EVALUATE",
        direct_answer="Het belangrijkste ontbrekende onderdeel van je plan is meer context.",
        main_observation="Je plan kan nog sterker worden met een duidelijker beoordelingskader.",
        claims=[
            ResponseClaim(
                claim_id="C1",
                claim_type="evaluation",
                text="Het plan mist nog context.",
                evidence_refs=["E1", "E2", "E3", "E4", "E5"],
                confidence="medium",
            )
        ],
        next_step=ReasoningNextStep(
            title="Werk je plan bij",
            instruction="Voeg één vervolgstap toe.",
            operation_type=None,
            target_entity_type="setup",
            target_entity_id="295",
            requires_confirmation=False,
        ),
        evidence_set_hash="hash-gate5",
        created_at=datetime.now(timezone.utc),
    )

    verifier = service._deterministic_verify(
        run=SimpleNamespace(
            id="run-gate5-generic",
            user_id=7,
            message="Bekijk mijn profiel, indicatoren, setup, strategie en gekoppelde bot. Wat is volgens jou op dit moment het belangrijkste ontbrekende onderdeel van mijn plan? Geef één concrete observatie en één vervolgstap.",
            conversation_id="conv-g5",
        ),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[
                SimpleNamespace(
                    evidence_id="E1",
                    domain="identity_context",
                    tool_name="read_profile",
                    entity_type="profile",
                    entity_id="7",
                    asset=None,
                    freshness="fresh",
                    confidence="high",
                    facts={"has_profile": True, "trader_profile": {"style": ["swing"], "risk_profile": "balanced"}},
                ),
                SimpleNamespace(
                    evidence_id="E2",
                    domain="market_context",
                    tool_name="read_indicator_configuration",
                    entity_type="indicator_configuration",
                    entity_id=None,
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={
                        "symbol": "BTC",
                        "technical": [{"indicator": "RSI"}],
                        "market": [{"indicator": "funding_rate"}],
                        "macro": [],
                        "configured_indicators": [
                            {"indicator": "RSI", "category": "technical"},
                            {"indicator": "funding_rate", "category": "market"},
                        ],
                    },
                ),
                SimpleNamespace(
                    evidence_id="E3",
                    domain="plan_context",
                    tool_name="read_active_setup",
                    entity_type="setup",
                    entity_id="295",
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={"setup_id": 295, "name": "BTC Swing 4H Gate Setup", "timeframe": "4H", "symbol": "BTC"},
                ),
                SimpleNamespace(
                    evidence_id="E4",
                    domain="plan_context",
                    tool_name="read_linked_strategy",
                    entity_type="strategy",
                    entity_id="311",
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={"strategy_id": 311, "setup_id": 295, "symbol": "BTC"},
                ),
                SimpleNamespace(
                    evidence_id="E5",
                    domain="automation_context",
                    tool_name="read_linked_bot",
                    entity_type="bot",
                    entity_id="172",
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={"bot_id": 172, "strategy_id": 311, "is_live": False},
                ),
            ],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-gate5", evidence_set_hash="hash-gate5", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.passed is False
    assert "response_insufficiently_personalized" in verifier.reason_codes
