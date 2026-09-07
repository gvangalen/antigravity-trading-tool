# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILDING` |
| Active goal | FINN V2 V1 action-contract completion batch |
| Candidate branch | `codex/finn-runtime-contract-authority-foundation` |
| Candidate SHA | `1bbab6bc15830cbb615e49006381e40996959153` (local action-contract candidate) |
| Production SHA | `dbd5d50438ae199549cb52ead942d09b475fda44` |
| Release owner | Build |
| Last updated | `2026-09-07` |

## Current Batch

- Goal: complete the existing FINN V2 V1 action contracts and route action
  inputs, proposals, confirmation, execution and result projections through
  the canonical operation registry.
- The latest local candidate persists every registry-approved final operation
  transition before contract-derived input collection, tools, policy or
  reasoning consume it. Portfolio reads and evaluations support the declared,
  owner-scoped optional asset filter.
- The canonical server-side Build smoke fixture is configured as a dedicated,
  non-admin fixture, separate from the unconfigured QA binding. Its identity
  is kept only in the server secret environment.
- The latest authenticated Build smoke functionally completed through the
  public V2 lifecycle. Its latency is recorded separately and is not treated
  as a statistical performance conclusion from a single run.
- Out of scope: QA-exclusive sealed holdout, official QA, product model
  changes.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Focused action-contract regressions | `PASS` | `75 passed` across registry, resolver, request preprocessing, runtime contract and portfolio adapter coverage on `1bbab6bc`. |
| Local FINN V2 schema health | `PASS` | Canonical local PostgreSQL migration sequence applied twice; `python3 -m backend.scripts.check_finn_v2_schema` passed on `1bbab6bc`. |
| Full canonical backend suite | `PASS` | `1740 passed, 3 skipped` from repository root on `1bbab6bc`. |
| Frontend contract checks | `PASS` | `npm run typecheck`, `npm run test:commands` (`5 passed`), `npm run test:i18n` (`7 passed`) and `npm run build` passed on `1bbab6bc`. |
| Real-provider validation | `NOT_RUN` | The local checkout has no configured provider credential or isolated server-eval procedure. No provider claim is made for `1bbab6bc`. |
| CI | `NOT_RUN` | No CI has been requested for action-contract candidate `1bbab6bc`; the recorded green CI belongs to production SHA `dbd5d504`. |
| Deployment | `NOT_RUN` | This content batch explicitly forbids deployment. |
| SHA identity | `PASS` | The currently live release remains `dbd5d50438ae199549cb52ead942d09b475fda44`; no candidate identity claim is made. |
| Authenticated functional Build smoke | `PASS` | Run `finn-v2-run-650a9df244ba48cf89f76c3e9a447818` completed `capability` with exactly one dispatch and one attempt; typed terminal projection matched the selected operation. |
| Latency observation | `RECORDED` | One functional smoke took about `29 s` from persisted creation to terminal persistence. A separate warm performance matrix is required after the content candidate is locally green. |
| Independent production QA | `NOT_STARTED` | User-controlled; Build did not start or contact QA. |

## Functional Build Smoke

- Tested SHA: `dbd5d50438ae199549cb52ead942d09b475fda44`.
- Run: `finn-v2-run-650a9df244ba48cf89f76c3e9a447818`.
- Terminal status: `completed`; initial/final operation: `capability`;
  canonical target: none.
- Dispatch claim: `2026-09-06T16:37:03Z`; terminal persistence:
  `2026-09-06T16:37:14Z`; created-to-terminal duration approximately `29 s`.
- Exactly one dispatch and one attempt. The terminal projection was typed; no
  proposal, execution, pending action, or bot activation was created.
- This is a functional smoke, not a p95 or maximum latency benchmark.

## Independent QA

- Tested SHA: `not started`.
- Holdout manifest/hash, report, report hash: `not started`.
- Verdict: `NOT_STARTED`.

## Action-Contract Validation And Performance

- The candidate preserves the existing operation registry as the only action
  authority. Runtime supplied inputs are recorded against that contract and
  `missing_inputs` are derived from its required inputs; no parallel guided
  field schema was introduced.
- `create_strategy`, setup/strategy updates, watchlist changes, score and
  portfolio reads/evaluations now use existing V2 proposal or read boundaries.
  Legacy `generate_strategy` remains unavailable to new V2 runs.
- The candidate remains a local Build artifact. It has no current CI,
  real-provider, deployment, live smoke, or independent-QA evidence and must
  not be treated as release-ready from its local results alone.
- Build must still run the separate warm runtime performance matrix and the
  non-sealed authenticated runtime coverage before any deployment or QA handoff.
- Independent QA remains `NOT_STARTED` and is not authorized by this status.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
