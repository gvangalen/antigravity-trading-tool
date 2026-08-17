from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

from backend.services.finn_v2_execution_gate_service import FinnV2ExecutionGateService


def test_execution_gate_blocks_when_payload_or_evidence_changed():
    service = FinnV2ExecutionGateService(session=object())
    service.flags.is_execution_gate_enabled = lambda: True
    service.flags.is_action_kill_switch_enabled = lambda: False
    service.flags.is_live_actions_enabled = lambda: False
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        policy_decision_id="policy-1",
        payload_json={"x": 2},
        payload_hash="different",
        evidence_set_hash="hash-a",
        requires_step_up_auth=False,
        operation_type="manual_order",
        status="confirmed",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.policies.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(policy_class="high_risk_action"))
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(confirmed=True))
    service.states.get_by_evidence_hash = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.eligibility.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))

    result = asyncio.run(service.check_execution_eligibility(user_id=7, run_id="run-1", proposal_id="proposal-1"))

    assert "proposal_payload_hash_mismatch" in result.blocking_codes
    assert "proposal_evidence_hash_mismatch" in result.blocking_codes
