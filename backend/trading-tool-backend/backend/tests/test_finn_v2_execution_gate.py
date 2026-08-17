from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

from backend.schemas.finn_v2_policy_schema import StepUpProof
from backend.services.finn_v2_execution_gate_service import FinnV2ExecutionGateService


def test_execution_gate_keeps_confirmed_proposal_ineligible_in_shadow():
    service = FinnV2ExecutionGateService(session=object())
    service.flags.is_execution_gate_enabled = lambda: True
    service.flags.is_action_kill_switch_enabled = lambda: True
    service.flags.is_live_actions_enabled = lambda: False
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        policy_decision_id="policy-1",
        payload_json={"x": 1},
        payload_hash=service._payload_hash({"x": 1}),
        evidence_set_hash="hash",
        requires_step_up_auth=True,
        operation_type="activate_live_bot",
        status="confirmed",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.policies.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(policy_class="high_risk_action"))
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(confirmed=True))
    service.states.get_by_evidence_hash = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-1", evidence_set_hash="hash"))
    service.validations.get_for_snapshot_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(evidence_set_hash="hash"))
    service.eligibility.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))

    result = asyncio.run(service.check_execution_eligibility(user_id=7, run_id="run-1", proposal_id="proposal-1", step_up_proof=None))

    assert result.eligible is False
    assert "kill_switch_enabled" in result.blocking_codes
    assert "step_up_required" in result.blocking_codes
