from types import SimpleNamespace

from backend.scripts.certify_finn_action_contracts import complete_card, has_measured_runtime_evidence
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_structured_operation_selector_service import (
    FinnV2StructuredOperationSelectorService,
)
from pathlib import Path


_COMMON = {
    "natural_language": True,
    "selector": True,
    "guided_state": True,
    "runtime_contract": True,
    "dispatch_attempt": True,
    "terminal_projection": True,
    "polling_sse": True,
    "negative_safety": True,
    "latency": True,
}


def test_write_card_requires_public_lifecycle_and_persistence_proof():
    contract = SimpleNamespace(mode="ACTION_PROPOSAL", supported=True)
    evidence = {"passed": True, "certification_card": dict(_COMMON)}

    assert not complete_card(evidence, contract)

    evidence["certification_card"].update({
        "proposal": True,
        "confirmation": True,
        "execution": True,
        "idempotency": True,
        "persistence": True,
    })
    assert complete_card(evidence, contract)


def test_read_card_requires_no_write_and_persistence_proof():
    contract = SimpleNamespace(mode="READ", supported=True)
    evidence = {"passed": True, "certification_card": dict(_COMMON, no_write=True)}

    assert not complete_card(evidence, contract)

    evidence["certification_card"]["persistence"] = True
    assert complete_card(evidence, contract)


def test_typed_unavailable_card_requires_limitation_and_no_write():
    contract = SimpleNamespace(mode="UNAVAILABLE", supported=True)
    evidence = {"passed": True, "certification_card": dict(_COMMON, no_write=True)}

    assert not complete_card(evidence, contract)

    evidence["certification_card"]["typed_limitation"] = True
    assert complete_card(evidence, contract)


def test_high_risk_action_is_certified_by_a_typed_non_execution_boundary():
    contract = SimpleNamespace(mode="ACTION_PROPOSAL", supported=True, policy_class="high_risk_action")
    evidence = {"passed": True, "certification_card": dict(
        _COMMON, typed_limitation=True, no_write=True, persistence=True,
    )}

    assert complete_card(evidence, contract)


def test_latest_report_registry_contract_has_multilingual_read_semantics():
    contract = FinnV2OperationRegistry().require_supported("read_latest_report")

    assert contract.action_polarity.value == "read"
    assert "Toon mijn laatste rapport." in contract.positive_examples
    assert len(contract.positive_examples) >= 3
    assert len(contract.negative_examples) == 3


def test_live_bot_activation_registry_contract_has_multilingual_safety_boundary():
    contract = FinnV2OperationRegistry().require_supported("activate_bot")

    assert len(contract.positive_examples) == 3
    assert len(contract.negative_examples) == 3


def test_paper_bot_activation_registry_contract_has_multilingual_boundary():
    contract = FinnV2OperationRegistry().require_supported("activate_paper_bot")

    assert len(contract.positive_examples) == 3
    assert len(contract.negative_examples) == 3


def test_previous_evidence_registry_contract_has_multilingual_follow_up_boundary():
    contract = FinnV2OperationRegistry().require_supported("explain_previous_evidence")

    assert len(contract.positive_examples) == 3
    assert len(contract.negative_examples) == 3


def test_registry_keeps_multilingual_selection_boundaries_for_certified_families():
    registry = FinnV2OperationRegistry()

    for operation_id in (
        "clarify_request",
        "unsupported_financial_operation",
        "evaluate_strategy",
        "evaluate_bot",
    ):
        assert len(registry.require_supported(operation_id).positive_examples) >= 3


def test_selector_manifest_projects_registry_selection_boundaries():
    contract = FinnV2OperationRegistry().require_supported("read_latest_report")
    manifest = FinnV2StructuredOperationSelectorService._selector_manifest((contract,))

    assert manifest[0]["positive_examples"] == list(contract.positive_examples)
    assert manifest[0]["negative_examples"] == list(contract.negative_examples)
    assert manifest[0]["selection_required_terms"] == list(contract.selection_required_terms)


def test_paper_activation_uses_the_existing_non_live_bot_mode():
    source = (Path(__file__).parents[1] / "services/finn_v2_action_adapter_registry.py").read_text()

    assert '"is_live": False, "mode": "manual", "is_active": True' in source
    assert '"is_live": False, "mode": "paper", "is_active": True' not in source


def test_paper_activation_certification_uses_a_neutral_fixture_name():
    source = (Path(__file__).parents[1] / "scripts/run_finn_v2_missing_contract_certification.py").read_text()

    assert "Matrix Paper Sandbox Bot" in source
    assert 'item.get("final_operation_id") == operation_id' in source


def test_multilingual_write_certification_accepts_projected_idempotent_draft():
    source = (Path(__file__).parents[1] / "scripts/run_finn_v2_write_language_certification.py").read_text()

    assert "proposal_lifecycle" in source
    assert "payload-hash" in source


def test_action_matrix_collects_guided_slots_one_turn_at_a_time():
    source = (Path(__file__).parents[1] / "scripts/run_finn_v2_full_action_matrix.py").read_text()

    assert "GUIDED_SLOT_ANSWERS" in source
    assert '"slot_turn_run_ids"' in source
    assert "_wait_for_runtime(base_url)" in source


def test_legacy_runtime_measurement_is_partial_not_not_tested():
    evidence = {"run_id": "finn-v2-run-measured", "runtime_contract_id": "contract-measured"}

    assert has_measured_runtime_evidence(evidence)


def test_write_card_does_not_pass_without_individual_guided_state_evidence():
    contract = SimpleNamespace(mode="ACTION_PROPOSAL", supported=True, required_inputs=("asset",))
    evidence = {"passed": True, "certification_card": dict(
        _COMMON,
        proposal=True,
        confirmation=True,
        execution=True,
        idempotency=True,
        persistence=True,
    )}
    evidence["certification_card"]["guided_state"] = False

    assert not complete_card(evidence, contract)
