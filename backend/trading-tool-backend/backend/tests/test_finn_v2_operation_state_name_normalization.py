from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService


def test_setup_name_drops_trailing_non_persistence_safety_instruction():
    assert FinnV2OperationStateService._trim_setup_name_clause(
        "Measured Accumulation without persisting it"
    ) == "Measured Accumulation"
