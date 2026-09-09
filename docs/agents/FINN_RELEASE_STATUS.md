# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILDING` |
| Active goal | FINN production write-action repair |
| Candidate branch | `codex/finn-1a73-production-write-repair` |
| Candidate SHA | `pending first repair commit` |
| Production SHA | `1a73b5bbc2ef43a952535df4ecae4511002178c2` |
| Release owner | Build |
| Last updated | `2026-09-09` |

## QA Runner

- QA runner readiness: `MATRIX_INTAKE_DEPLOYED`
- authenticated QA preflight: completed for the production SHA by the
  independent workflow; Build does not access `FINN_QA_USER_ID`.
- official QA status: `NOT_ACCEPTED` for production SHA `1a73b5bbc2ef43a952535df4ecae4511002178c2`.

The protected GitHub Actions runner is the canonical authenticated production
QA executor. The candidate adds encrypted QA-owned manifest intake and an
explicit safe-fixture action boundary. The active QA goal supplies the full
SHA; its preflight must prove that the production checkout, release marker,
backend health, and frontend build-info all match it. This avoids treating a
committed status file as a self-referential release marker.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Production diagnosis | `FAIL` | Independent QA workflow `34355138568` observed proposal-producing actions terminating as `orchestrator_failed` on the production SHA. |
| Production-like regression | `PASS` | A disabled proposal policy now yields typed `downgraded` / `proposals_disabled`; enabled proposals terminalize with one dispatch and one attempt. |
| Sequential local action chain | `PASS` | `16/16` natural-language steps from a fresh synthetic user, without pre-seeding downstream IDs; artifact `/tmp/finn-1a73-sequential-action-chain.json`, SHA-256 `1ef1ae6ab10eecd0fff423c7af4c0fd69b657eddd0f07227ef865d988bc01dd3`. |
| Provider development/regression | `PASS` | `18/18` development and `102/102` regression with the real provider on the repair checkout. |
| Backend suite | `PASS` | `1848 passed, 3 skipped` on the repair checkout. |
| CI | `NOT_RUN` | Awaiting the bounded repair commit. |
| Deployment | `NOT_RUN` | The production SHA remains the failed QA baseline. |
| Official independent QA | `NOT_STARTED` | No new official QA may start until this repair is deployed and its limited Build diagnosis is green. |

## Independent QA

- Tested SHA: `1a73b5bbc2ef43a952535df4ecae4511002178c2`.
- Holdout manifest/hash, report, report hash: retained by QA; Build does not
  read or use sealed QA material.
- Verdict: `NOT_ACCEPTED`; no subsequent official QA run is authorized during
  this repair cycle.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
