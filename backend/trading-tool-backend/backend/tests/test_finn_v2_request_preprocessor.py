from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService


def test_autonomous_financial_delegation_is_a_financial_execution_fact():
    facts = FinnV2RequestPreprocessorService().preprocess(
        message="Move my savings into whichever digital asset you expect to rise tomorrow."
    )

    assert facts.financial_execution_intent is True
    assert facts.action_polarity == "execute"


def test_non_financial_move_request_remains_outside_the_financial_execution_boundary():
    facts = FinnV2RequestPreprocessorService().preprocess(
        message="Move my calendar appointment to tomorrow."
    )

    assert facts.financial_execution_intent is False
