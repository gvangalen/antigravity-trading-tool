# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILDING` |
| Active goal | FINN V2 content and state repair batch |
| Candidate branch | `codex/finn-runtime-contract-authority-foundation` |
| Candidate SHA | `e871f5e0e2077799f8e866915e3ecf42b2dc7775` |
| Production SHA | `dbd5d50438ae199549cb52ead942d09b475fda44` |
| Release owner | Build |
| Last updated | `2026-09-06` |

## Current Batch

- Goal: repair conversation/evidence lineage, persisted contract context for
  model reasoning, guided setup continuation, operation selection, compound
  `EVALUATE`, and bot consequence as one local content batch.
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
| Focused regressions | `PASS` | `130 passed` across orchestrator, runtime-contract, classifier, resolver, and proposal coverage. |
| Full relevant suite | `PASS` | `1708 passed, 3 skipped` on the current candidate worktree (product code `e871f5e0`). |
| Real-provider selector canary | `PASS` | Isolated candidate worktree: structured response `completed`, parsed, `explain_financial_concept`, concept `RSI`. |
| Real-provider development selector set | `PASS` | `18/18`; all scored dimensions 100%; zero provider/schema/parse/validation/timeout failures; p95 `3.848 s`. |
| Real-provider regression selector set | `PASS` | `102/102`; all scored dimensions 100%; zero provider/schema/parse/validation/timeout failures; p95 `3.366 s`. |
| CI | `PASS` | Run `34045566111`, exact candidate SHA. |
| Deployment | `PASS` | Auto Deploy `34045675870`, exact candidate SHA. |
| SHA identity | `PASS` | Production checkout, release marker, public backend, and frontend all reported `dbd5d50438ae199549cb52ead942d09b475fda44`. |
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

## Content Validation And Performance

- The candidate persists continuation lineage and guided state from the prior
  runtime contract instead of selecting the just-created child contract. Its
  durable lineage also uses the immutable contract target rather than a late
  tool or workspace projection.
- Build must still run the separate warm runtime performance matrix and the
  non-sealed authenticated runtime coverage before any deployment or QA handoff.
- Independent QA remains `NOT_STARTED` and is not authorized by this status.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
