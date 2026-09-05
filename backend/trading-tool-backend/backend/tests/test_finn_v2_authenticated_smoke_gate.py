from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.scripts.run_finn_v2_authenticated_smoke_gate import _assert_persisted_smoke


def _run_result():
    return {
        "run_id": "finn-v2-run-smoke-1",
        "contract_id": "finn-v2-contract-smoke-1",
        "status": "completed",
        "polling_sse_contract_projection": True,
    }


def _contract(*, projection=None):
    return SimpleNamespace(
        run_id="finn-v2-run-smoke-1",
        terminal_projection_json=projection if projection is not None else {
            "run_id": "finn-v2-run-smoke-1",
            "terminal_status": "completed",
            "terminal_response_type": "response",
        },
    )


def test_authenticated_smoke_requires_contract_typed_projection_and_one_dispatch():
    result = _assert_persisted_smoke(
        run_result=_run_result(),
        persisted={
            "contract": _contract(),
            "dispatches": [SimpleNamespace(dispatch_id="dispatch-smoke-1", attempt_count=1)],
        },
    )

    assert result["persistence_verified"] is True
    assert result["terminal_projection_typed"] is True
    assert result["dispatch_count"] == 1
    assert result["dispatch_attempt_count"] == 1


@pytest.mark.parametrize(
    ("persisted", "error_code"),
    [
        ({"contract": None, "dispatches": []}, "runtime_contract_missing"),
        ({"contract": _contract(projection={}), "dispatches": []}, "typed_terminal_projection_missing"),
        ({"contract": _contract(), "dispatches": []}, "dispatch_count_0"),
        ({"contract": _contract(), "dispatches": [SimpleNamespace(dispatch_id="a", attempt_count=1), SimpleNamespace(dispatch_id="b", attempt_count=1)]}, "dispatch_count_2"),
        ({"contract": _contract(), "dispatches": [SimpleNamespace(dispatch_id="a", attempt_count=2)]}, "dispatch_attempt_count_exceeded"),
    ],
)
def test_authenticated_smoke_fails_closed_on_incomplete_persistence(persisted, error_code):
    with pytest.raises(AssertionError, match=error_code):
        _assert_persisted_smoke(run_result=_run_result(), persisted=persisted)
