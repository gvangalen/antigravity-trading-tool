# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | Protected FINN production-QA matrix runner |
| Candidate branch | `codex/finn-production-qa-matrix-runner` |
| Candidate SHA | `runtime marker verified during QA preflight` |
| Production SHA | `runtime marker verified during QA preflight` |
| Release owner | Build |
| Last updated | `2026-09-07` |

## QA Runner

- QA runner readiness: `MATRIX_INTAKE_DEPLOYED`
- authenticated QA preflight: `PASS` — workflow `34149205266` on production SHA
  `3c53513c8bcd9d2a6211eb65c1ce4c1e374fddf0`; authentication only, no content cases
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
| Focused runner tests | `PASS` | `15 passed`: encrypted intake, redaction, profile validation, action boundary, release-marker parsing. |
| CI | `PASS` | GitHub Actions `34150714774` for the matrix-runner implementation. |
| Deployment | `PASS` | Auto Deploy `34150840370`; public backend and frontend markers matched before this status-only update. |
| Official independent QA | `NOT_STARTED` | User-authorized QA must provide its own goal and manifest. |

## Independent QA

- Tested SHA: `not started`.
- Holdout manifest/hash, report, report hash: `not started`.
- Verdict: `NOT_STARTED`.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
