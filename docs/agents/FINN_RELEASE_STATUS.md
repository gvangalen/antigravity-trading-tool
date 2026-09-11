# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILD_VALIDATED` |
| Active goal | FINN production reliability and parity repair |
| Candidate branch | `codex/finn-345660-reliability-parity-repair` |
| Candidate code SHA | `af26ccd7582f3b63a9adbef6cc6fa87d4d21c767` |
| Production SHA | `34f00d18b27c727788f5e3e95db720e3fa0f06c5` |
| Release owner | Build |
| Last updated | `2026-09-11` |

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
| Public production-equivalent matrices | `PASS` | Three independent fresh namespaces: each `37/37`, `16/16` write actions, `9/9` persisted lineage, polling/SSE parity, one dispatch/attempt, and all 37 original HTTP statuses `200` with zero retries. Artifacts: `/tmp/finn-345660-local/final-parity-{3,4,5}.json`. |
| Provider development | `PASS` | Real provider `18/18`, all measured accuracies `100%`; provider/schema/parse/validation/timeout failures `0%`. Artifact `/tmp/finn-345660-local/final-provider-development-af26.json`, SHA-256 `9c9d679aaac60eefd4bbf2d819a9356198b8754dbb4b6e5acd6dbc3bb584a681c`. |
| Provider regression | `PASS` | Real provider `102/102`, all measured accuracies `100%`; provider/schema/parse/validation/timeout failures `0%`. Artifact `/tmp/finn-345660-local/final-provider-regression-af26.json`, SHA-256 `3e5dca12bc4ab1890407095887e3b1097f7c32d54ccef32629e6ec011afcc99a`. |
| Backend suite | `PASS` | `1887 passed, 3 skipped` from the canonical checkout root. |
| Frontend suite | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, and `audit:high` passed. |
| CI | `NOT_RUN` | Awaiting the validated candidate push. |
| Deployment | `NOT_RUN` | Production remains on the prior release until Auto Deploy completes. |
| Official independent QA | `NOT_STARTED` | Build does not initiate official QA. |

## Independent QA

- No independent QA has been started for this candidate.
- The sealed holdout remains QA-exclusive and was not read or used by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
