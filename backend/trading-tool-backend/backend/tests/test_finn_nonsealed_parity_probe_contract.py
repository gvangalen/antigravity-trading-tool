from backend.scripts.run_finn_v2_nonsealed_parity_matrix import _probe_contract


def _record(*, names=(), answer="Checked.", proposal=None):
    return {
        "runtime_state": {"responses_exchange": {
            "answer": answer,
            "tool_trace": [{"name": name, "status": "completed"} for name in names],
        }},
        "proposal": proposal,
    }


def _observed(*, status="completed", operation=None, parity=True):
    return {
        "status": status,
        "final_operation_id": operation,
        "polling_sse_contract_projection": parity,
    }


def test_model_led_read_requires_the_correct_tool_and_answer():
    expected = "read_portfolio"
    assert _probe_contract("portfolio", expected, _observed(),
                           _record(names=("get_portfolio_and_exposure",)))[0]
    assert not _probe_contract("portfolio", expected, _observed(), _record())[0]
    assert not _probe_contract("portfolio", expected, _observed(),
                               _record(names=("get_current_asset_scores",)))[0]
    assert not _probe_contract("portfolio", expected, _observed(),
                               _record(names=("get_portfolio_and_exposure",), answer=""))[0]


def test_read_rejects_proposal_or_write_tool():
    observed = _observed()
    assert not _probe_contract("portfolio", "read_portfolio", observed,
                               _record(names=("get_portfolio_and_exposure",), proposal={"id": 1}))[0]
    assert not _probe_contract("portfolio", "read_portfolio", observed,
                               _record(names=("get_portfolio_and_exposure", "manage_paper_bot_proposal")))[0]


def test_guided_setup_keeps_operation_contract():
    record = _record(names=("create_or_update_trade_plan_proposal",))
    assert _probe_contract("guided_setup", "create_setup",
                           _observed(status="clarification_required", operation="create_setup"), record)[0]
    assert not _probe_contract("guided_setup", "create_setup",
                               _observed(status="clarification_required"), record)[0]


def test_direct_answer_and_unsafe_request_have_safety_boundary():
    assert _probe_contract("capability", "capability", _observed(), _record())[0]
    assert not _probe_contract("capability", "capability", _observed(),
                               _record(names=("manage_paper_bot_proposal",)))[0]
    assert _probe_contract("unsupported", "unsupported_financial_operation",
                           _observed(status="clarification_required"), _record())[0]
    assert not _probe_contract("unsupported", "unsupported_financial_operation",
                               _observed(), _record(proposal={"id": 1}))[0]
