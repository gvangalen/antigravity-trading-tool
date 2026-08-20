from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

from backend.schemas.finn_v2_policy_schema import StepUpProof
from backend.infrastructure.repositories.finn_v2_eligibility_repository import FinnV2EligibilityRepository
from backend.services.finn_v2_json_safety import to_json_safe
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


def test_execution_gate_allows_confirmed_watchlist_change_as_safe_allowlisted_action():
    service = FinnV2ExecutionGateService(session=object())
    service.flags.is_execution_gate_enabled = lambda: True
    service.flags.is_action_kill_switch_enabled = lambda: True
    service.flags.execute_watchlist_changes_enabled = lambda: True
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        policy_decision_id="policy-1",
        payload_json={"change": {"asset": "ETH", "operation": "add"}},
        payload_hash=service._payload_hash({"change": {"asset": "ETH", "operation": "add"}}),
        evidence_set_hash="hash",
        requires_step_up_auth=False,
        operation_type="watchlist_add",
        status="confirmed",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.policies.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(policy_class="proposal"))
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(confirmed=True))
    service.states.get_by_evidence_hash = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-1", evidence_set_hash="hash"))
    service.validations.get_for_snapshot_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(evidence_set_hash="hash"))
    service.eligibility.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))

    result = asyncio.run(service.check_execution_eligibility(user_id=7, run_id="run-1", proposal_id="proposal-1"))

    assert result.eligible is True
    assert result.blocking_codes == []


def test_execution_gate_repository_serializes_decision_json_before_flush():
    captured = {}

    class _RepoSession:
        def add(self, row):
            captured["row"] = row

        async def flush(self):
            return None

    repo = FinnV2EligibilityRepository(_RepoSession())
    decision_json = {
        "eligible": True,
        "checked_at": datetime.now(timezone.utc),
        "blocking_codes": [],
    }

    row = asyncio.run(
        repo.create(
            id="eligibility-1",
            proposal_id="proposal-1",
            run_id="run-1",
            user_id=7,
            eligible=True,
            policy_class="proposal",
            decision_json=decision_json,
            eligibility_version="2026-08-17.block5",
        )
    )

    assert row.decision_json == to_json_safe(decision_json)
    assert isinstance(row.decision_json["checked_at"], str)
