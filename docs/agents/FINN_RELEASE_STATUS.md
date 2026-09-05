# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LIVE_SMOKE_RUNNING` |
| Active goal | FINN V2 repair batch; authenticated Build smoke fixture binding |
| Candidate branch | `main` |
| Candidate SHA | `e04e39c5141c41ed0ff68bdcfb512ffef53f6785` |
| Production SHA | `e04e39c5141c41ed0ff68bdcfb512ffef53f6785` |
| Release owner | Build |
| Last updated | `2026-09-05 14:45 UTC` |

## Current Batch

- Goal: terminal lifecycle, lineage, guided setup, selector, and latency
  repair validation.
- The canonical server-side Build smoke fixture is configured as a dedicated,
  non-admin fixture, separate from the unconfigured QA binding. Its identity
  is kept only in the server secret environment.
- Current blocking failure: the first smoke on this release claimed exactly
  one dispatch but reached `lifecycle_deadline_exceeded` before terminal
  capability delivery.
- Out of scope: QA-exclusive sealed holdout, official QA, product model
  changes.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Focused regressions | `PASS` | 108 targeted tests for the final safety boundary. |
| Full relevant suite | `PASS` | `1682 passed, 3 skipped` on `e04e39c5`. |
| Real provider | `PASS` | Development 18/18; regression 102/102; p95 3.671 s and 3.345 s; zero provider/schema/parse/validation/timeout failures. |
| CI | `PASS` | Run `33972113599`, exact candidate SHA. |
| Deployment | `PASS` | Auto Deploy `33972205371`, exact candidate SHA. |
| SHA identity | `PASS` | `github/main`, production checkout, public backend, and frontend reported `e04e39c5`. |
| Authenticated live smoke | `FAIL` | One generic capability run claimed one dispatch, then terminalized as `lifecycle_deadline_exceeded`; no proposal, execution, or pending action was created. |
| Independent production QA | `NOT_STARTED` | User-controlled; prohibited until the live smoke is measurable and passes. |

## Live Smoke

- Tested SHA: `e04e39c5141c41ed0ff68bdcfb512ffef53f6785`.
- The generic capability run had one dispatch and one attempt, but its terminal
  projection was a typed failure due to `lifecycle_deadline_exceeded`; the
  polling/SSE success gate is therefore not passed. Fixture write snapshot
  remained empty for proposals, executions, and pending actions.

## Independent QA

- Tested SHA: `not started`.
- Holdout manifest/hash, report, report hash: `not started`.
- Verdict: `NOT_STARTED`.

## Next Owner Action

Build repairs the bounded lifecycle path that exceeds its deadline after the
worker claims an interactive run. No QA may start until a fresh, measured
generic Build smoke passes.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
