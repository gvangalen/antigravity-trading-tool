# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILD_VALIDATED` |
| Active goal | FINN Today finalized briefing and locale repair |
| Candidate branch | `codex/finn-today-final-briefing` |
| Candidate code SHA | `18df0f34ce0a0a64887f5a94a7e296078a5f678d` |
| Production SHA | `77ed2738eac91e0f8c6c94eb9e576d1f6790d3d0` |
| Release owner | Build |
| Last updated | `2026-09-18` |

## QA Runner

- QA runner readiness: `AVAILABLE`
- authenticated QA preflight: not started for this candidate; Build does not
  access `FINN_QA_USER_ID`.
- official QA status: `NOT_STARTED` for this candidate.

The protected GitHub Actions runner is the canonical authenticated production
QA executor. The candidate adds encrypted QA-owned manifest intake and an
explicit safe-fixture action boundary. The active QA goal supplies the full
SHA; its preflight must prove that the production checkout, release marker,
backend health, and frontend build-info all match it. This avoids treating a
committed status file as a self-referential release marker.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| FINN Today finalization | `PASS` | A queued/generating briefing immediately projects the current personal fallback, compact preview polling remains active, and locale copy replaces backend loading/status text; focused backend `29/29` and frontend `6/6`. |
| Provider development | `PASS` | Real provider `18/18`, no retries or provider/schema/parse/validation/timeout failures; artifact `/tmp/finn-today-final-provider-development.json`, SHA-256 `32c731c7266e2fca1eb51fbe6868f46691604208d9d172fbb02e153e561618dd`. |
| Provider regression | `PASS` | Real provider `109/109`, no retries or provider/schema/parse/validation/timeout failures; artifact `/tmp/finn-today-final-provider-regression.json`, SHA-256 `77cd5dd3ddd2e40f70f3f996dcb2273de6348d05ae6f670d839506685ade909f`. |
| Backend suite | `PASS` | `2173 passed, 3 skipped` from the canonical checkout root. |
| Frontend suite | `PASS` | `typecheck`, `lint:i18n`, `test:i18n` (`7/7`), `test:commands` (`5/5`), `audit:high`, and production build passed. |
| CI | `NOT_RUN` | Awaiting the validated candidate push. |
| Deployment | `NOT_RUN` | Production remains on the prior release until Auto Deploy completes. |
| Official independent QA | `NOT_STARTED` | Build does not initiate official QA. |

## Independent QA

- No independent QA has been started for this candidate.
- The sealed holdout remains QA-exclusive and was not read or used by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
