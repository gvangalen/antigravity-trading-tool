# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LIVE_SMOKE_RUNNING` |
| Active goal | FINN V2 repair batch; authenticated live smoke fixture binding |
| Candidate branch | `main` |
| Candidate SHA | `61571ed7ccbb0d48b6cee79446114090ca2ad829` |
| Production SHA | `61571ed7ccbb0d48b6cee79446114090ca2ad829` |
| Release owner | Build |
| Last updated | `2026-09-05 14:05 UTC` |

## Current Batch

- Goal: terminal lifecycle, lineage, guided setup, selector, and latency
  repair validation.
- Known operational blocker: the canonical server-side QA fixture binding is
  not yet configured; no account may be selected by heuristic.
- Out of scope: sealed-holdout tuning, official QA, product model changes.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Focused regressions | `PASS` | 108 targeted tests for the final safety boundary. |
| Full relevant suite | `PASS` | `1682 passed, 3 skipped` on `61571ed7`. |
| Real provider | `PASS` | Development 18/18; regression 102/102; p95 3.671 s and 3.345 s; zero provider/schema/parse/validation/timeout failures. |
| CI | `PASS` | Run `33965640410`, exact candidate SHA. |
| Deployment | `PASS` | Auto Deploy `33965733731`, exact candidate SHA. |
| SHA identity | `PASS` | `origin/main`, production checkout, public backend, frontend, and deploy status reported `61571ed7`. |
| Authenticated live smoke | `NOT_MEASURABLE` | Blocked before run creation: no canonical `FINN_QA_USER_ID`; documented legacy fixture is absent. |
| Independent production QA | `NOT_STARTED` | User-controlled; prohibited until the live smoke is measurable and passes. |

## Live Smoke

- Tested SHA: `not run`.
- Run IDs, terminalization, polling/SSE, dispatch/attempt, safety, latency:
  `not measurable` until the canonical fixture binding exists.

## Independent QA

- Tested SHA: `not started`.
- Holdout manifest/hash, report, report hash: `not started`.
- Verdict: `NOT_STARTED`.

## Next Owner Action

Operations configures and verifies the server-side `FINN_QA_USER_ID` binding
under the QA fixture contract. Build then runs the bounded authenticated live
smoke; only a measured passing smoke can move this status to
`READY_FOR_INDEPENDENT_QA`.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
