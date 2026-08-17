# FINN Core V2 Cutover Runbook

## Goal

Block 8 keeps FINN Core V2 in a controlled rollout state. V1 stays the default path until operators explicitly enable each gate and verify the latest eval evidence.

## Safety Baseline

- `FINN_V2_RUNTIME_MODE` defaults to `v1_primary`.
- Visible V2 proposals, confirmation routes, and action execution stay off by default.
- Only verified responses may be delivered to users.
- V1 remains the immediate fallback whenever V2 visible delivery fails with a technical error and fallback is enabled.
- Production cutover is never automatic.

## Operator Sequence

1. Apply migration `2026_08_17_finn_v2_evals_cutover_execution.py`.
2. Run the golden dataset in `mock` mode:
   `python3 backend/trading-tool-backend/backend/scripts/run_finn_v2_golden_eval.py --persist-results`
3. Run the golden dataset in `real` mode only when AI runtime credentials are available:
   `python3 backend/trading-tool-backend/backend/scripts/run_finn_v2_golden_eval.py --model-mode real --persist-results`
4. Evaluate release gates:
   `python3 backend/trading-tool-backend/backend/scripts/run_finn_v2_release_gate.py`
5. Verify operator status endpoints:
   - `GET /system/finn-v2/runtime`
   - `GET /system/finn-v2/status`
6. Enable shadow comparison first.
7. Enable canary readonly mode for a narrow allowlist or percentage.
8. Enable visible proposals only after release gates pass.
9. Enable confirmation routes only after visible proposals are stable.
10. Enable specific action adapters one by one, starting with paper-safe operations.

## Required Release Evidence

- Latest golden dataset results persisted.
- Release gate result persisted and passing.
- No blocked real-model validation if production approval is being requested.
- Shadow comparisons do not show unsafe execution language or account/entity drift.
- Account isolation checks pass for visible delivery, proposals, confirmation, and execution.

## Rollback

- Set `FINN_V2_RUNTIME_MODE=v1_primary`.
- Leave `FINN_V2_V1_FALLBACK_ENABLED=true`.
- Disable `FINN_V2_VISIBLE_PROPOSALS_ENABLED`, `FINN_V2_CONFIRMATION_ROUTES_ENABLED`, and `FINN_V2_ACTION_EXECUTION_ENABLED`.
- Disable any operation-specific execute flags that were turned on.

## Notes

- If the real-model eval is blocked because the AI runtime is unavailable, the gate result must be treated as non-approving for production cutover.
- Mobile and frontend surfaces do not select V1 or V2 locally; backend runtime selection is authoritative.
