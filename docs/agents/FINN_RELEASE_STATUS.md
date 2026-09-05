# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | FINN V2 bounded lifecycle and authenticated Build-smoke repair |
| Candidate branch | `main` |
| Candidate SHA | `59311eb4b80b442ad67ed5791fca40a35ac5f917` |
| Production SHA | `59311eb4b80b442ad67ed5791fca40a35ac5f917` |
| Release owner | Build |
| Last updated | `2026-09-05 18:33 UTC` |

## Current Batch

- Goal: separate queue/context/selector/post-selection boundaries and prove
  the generic authenticated capability lifecycle.
- The canonical server-side Build smoke fixture is configured as a dedicated,
  non-admin fixture, separate from the unconfigured QA binding. Its identity
  is kept only in the server secret environment.
- Completed repair: context hydration now precedes the bounded selector phase;
  the selector has an independent 35-second phase with a two-second terminal
  persistence reserve; the post-selection capability path skips tool,
  reasoning and verifier work.
- The public polling projection accepts the deterministic
  `registry_grounded` capability verifier status and the smoke observer safely
  retries transient gateway responses without creating another run.
- Out of scope: QA-exclusive sealed holdout, official QA, product model
  changes.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Focused regressions | `PASS` | `29 passed` across runtime contract, smoke, provider, and persisted runtime gate tests. |
| Full relevant suite | `PASS` | `1688 passed, 3 skipped` on `59311eb4`. |
| CI | `PASS` | Run `33983528129`, exact candidate SHA. |
| Deployment | `PASS` | Auto Deploy `33983632392`, exact candidate SHA. |
| SHA identity | `PASS` | `github/main`, production checkout, public backend, and frontend reported `59311eb4`. |
| Authenticated live smoke | `PASS` | Generic capability run completed with one dispatch and one attempt; persisted projection, polling, and SSE matched. |
| Independent production QA | `NOT_STARTED` | User-controlled; Build did not start or contact QA. |

## Live Smoke

- Tested SHA: `59311eb4b80b442ad67ed5791fca40a35ac5f917`.
- Run: `finn-v2-run-50687844d17a439c8cd17c12aa8a5d5d`.
- Terminal status: `completed`; initial/final operation: `capability`;
  canonical target: none.
- Queue/claim wait: `7.94 s`; active processing to terminal: `16.29 s`;
  external authenticated observation: `38.495 s`.
- Exactly one dispatch and one attempt. The terminal projection was typed and
  identical through polling and SSE. No proposal, execution, pending action,
  or bot activation was created.

## Independent QA

- Tested SHA: `not started`.
- Holdout manifest/hash, report, report hash: `not started`.
- Verdict: `NOT_STARTED`.

## Next Owner Action

The bounded lifecycle repair has passed its Build smoke. Only the user may
start an independent QA assignment; Build must not contact or direct QA.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
