# FINN Core V2 Legacy Retirement Matrix

## Principle

Legacy V1 paths remain active until each V2 surface proves parity or better under evals, shadow comparison, and operator review.

| Surface | V2 Block 8 Status | Retirement Condition | Current Action |
| --- | --- | --- | --- |
| Assistant chat | Runtime selector wired | Passing golden evals and release gates, stable canary readonly behavior | Keep V1 primary |
| Assistant stream | Visible delivery wired | Same as chat plus SSE parity validation | Keep V1 primary |
| Mission Control | Read-only V2 delivery wired | Stable verified response delivery and fallback contract | Keep V1 primary |
| Proposal visibility | Route gated | Visible proposals explicitly enabled after canary review | Keep disabled |
| Confirmation | Route gated | Confirmation routes enabled after proposal review | Keep disabled |
| Execution | Adapter registry and execution service wired | Per-operation approval, paper-safe validation, operator signoff | Keep disabled |
| Live actions | Safety-gated only | Separate approval after explicit live-action readiness review | Keep disabled |

## Legacy Retirement Rules

- Never retire V1 while `FINN_V2_RUNTIME_MODE` is `v1_primary` or `v1_primary_v2_shadow`.
- Do not retire legacy proposal or execution flows just because readonly V2 delivery is stable.
- Keep fallback behavior until post-cutover monitoring shows V2 is stable and the rollback path is rehearsed.
- Retire one surface at a time; avoid all-at-once cutovers.

## Evidence Needed Before Removing Legacy Code

- Production real-model eval success on the latest golden set.
- Release gate pass on the same eval run.
- Clean shadow comparison sample for the target surface.
- Account isolation and action safety checks passing.
- Runbook updated with the exact flag state used for cutover.
