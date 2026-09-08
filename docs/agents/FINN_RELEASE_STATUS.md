# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | FINN action-contract runtime repair |
| Candidate branch | `codex/finn-bb63-qa-repair` |
| Candidate SHA | `a5781630ac3077050bd8be434cb659c668a0f2fa` |
| Production SHA | `a5781630ac3077050bd8be434cb659c668a0f2fa` |
| Release owner | Build |
| Last updated | `2026-09-08` |

## QA Runner

- QA runner readiness: `MATRIX_INTAKE_DEPLOYED`
- authenticated QA preflight: `NOT_RUN` for the active release; QA owns this
  live check through `FINN_QA_USER_ID` and its active QA goal.
- official QA status: `NOT_STARTED`

The protected GitHub Actions runner is the canonical authenticated production
QA executor. The candidate adds encrypted QA-owned manifest intake and an
explicit safe-fixture action boundary. The active QA goal supplies the full
SHA; its preflight must prove that the production checkout, release marker,
backend health, and frontend build-info all match it. This avoids treating a
committed status file as a self-referential release marker.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Local action matrix | `PASS` | `16/16` worker-driven action contracts; artifact SHA-256 `c338b3ec37b723377b6395090e16576d5e3f95ffa39f79be7ecbb9b0dc4fcc61`. |
| Provider development/regression | `PASS` | `18/18` development and `102/102` regression with real provider. |
| Backend suite | `PASS` | `1835 passed, 3 skipped`. |
| CI | `PASS` | GitHub Actions `34266409708` for `a5781630ac3077050bd8be434cb659c668a0f2fa`. |
| Deployment | `PASS` | Auto Deploy `34266601125`; public backend health `200` and frontend build-info both reported the production SHA. |
| Official independent QA | `NOT_STARTED` | User-authorized QA must provide its own goal and manifest. |

## Independent QA

- Tested SHA: `not started`.
- Holdout manifest/hash, report, report hash: `not started`.
- Verdict: `NOT_STARTED`.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
