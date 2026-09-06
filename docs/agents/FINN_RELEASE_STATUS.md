# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILDING` |
| Active goal | FINN V2 content and state repair batch |
| Candidate branch | `codex/finn-runtime-contract-authority-foundation` |
| Candidate SHA | `f9b5d9f6d8656e365a20af3728ae4a4e459c4c7d` |
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
| Focused runtime/content regressions | `PASS` | `272 passed` across lineage, guided state, operation selection, executor, verifier, and terminal transport coverage. |
| Registry and selector-contract validation | `PASS` | Registry validator: `96` cases; contract/selector tests: `56 passed`. |
| Full relevant suite | `PASS` | `1708 passed, 3 skipped` on `f9b5d9f6`. |
| Real-provider selector canary | `PASS` | Isolated product-code worktree `e871f5e0`: structured response `completed`, parsed, `explain_financial_concept`, concept `RSI`. `f9b5d9f6` adds test/status evidence only. |
| Real-provider development selector set | `PASS` | Isolated product-code worktree `e871f5e0`: `18/18`; all scored dimensions 100%; zero provider/schema/parse/validation/timeout failures; p95 `3.848 s`. |
| Real-provider regression selector set | `PASS` | Isolated product-code worktree `e871f5e0`: `102/102`; all scored dimensions 100%; zero provider/schema/parse/validation/timeout failures; p95 `3.366 s`. |
| CI | `NOT_RUN` | No CI has been requested for candidate `f9b5d9f6`; the recorded green CI belongs to production SHA `dbd5d504`. |
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

## Content Validation And Performance

- The candidate persists continuation lineage and guided state from the prior
  runtime contract instead of selecting the just-created child contract. Its
  durable lineage also uses the immutable contract target rather than a late
  tool or workspace projection.
- The candidate remains a local Build artifact. It has no current CI,
  deployment, live smoke, or independent-QA evidence and must not be treated
  as release-ready from its local results alone.
- Build must still run the separate warm runtime performance matrix and the
  non-sealed authenticated runtime coverage before any deployment or QA handoff.
- Independent QA remains `NOT_STARTED` and is not authorized by this status.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
