# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | FINN V2 full action-contract completion batch |
| Candidate branch | `codex/finn-runtime-contract-authority-foundation` |
| Live application SHA | `5735c004fa6d0545ae852b2a795386ae647c48f0` |
| Release ancestry | `github/main` and `github/codex/finn-runtime-contract-authority-foundation` both resolve to the live application SHA |
| Release owner | Build |
| Last updated | `2026-09-07` |

The live application SHA is the only FINN production test target. A later
metadata-only checkout used to read this status document is not a second
release candidate. QA must identify the GitHub remote by URL; a local remote
named `origin` is not release evidence.

## Current Batch

- Goal: complete the existing FINN V2 action contracts and route action
  inputs, proposals, confirmation, execution and result projections through
  the canonical operation registry.
- The deployed candidate persists every registry-approved final operation
  transition before contract-derived input collection, tools, policy or
  reasoning consume it. Portfolio reads and evaluations support the declared,
  owner-scoped optional asset filter.
- The canonical server-side Build smoke fixture is configured as a dedicated,
  non-admin fixture, separate from the unconfigured QA binding. Its identity
  is kept only in the server secret environment.
- The latest authenticated Build smoke functionally completed through the
  public V2 lifecycle. Its latency is recorded separately and is not treated
  as a statistical performance conclusion from a single run.
- Proposal publication, confirmation and execution now append safe lifecycle
  provenance to the originating runtime contract and refresh its one persisted
  terminal projection; they do not introduce action fields or token material.
- Out of scope: QA-exclusive sealed holdout, official QA, product model
  changes and direct broker/exchange execution.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Focused action-contract regressions | `PASS` | `104 passed` across registry, runtime contract, guided state, proposal, confirmation, execution, adapter, source and portfolio coverage. |
| Non-sealed selector registry | `PASS` | `120` development, regression and published-regression cases validated against the current registry; no sealed QA holdout was loaded. |
| Local FINN V2 schema health | `PASS` | Canonical local PostgreSQL migration sequence applied twice; `python3 -m backend.scripts.check_finn_v2_schema` passed on `1bbab6bc`. |
| Full canonical backend suite | `PASS` | `1749 passed, 3 skipped` from repository root on the action-contract and migration candidate. |
| Frontend contract checks | `PASS` | `npm run typecheck`, `npm run test:commands` (`5 passed`), `npm run test:i18n` (`7 passed`) and `npm run build` passed. |
| CI | `PASS` | GitHub Actions run `34118073894` succeeded for the live application SHA. |
| Deployment | `PASS` | Auto Deploy run `34118232654` succeeded for the live application SHA. |
| SHA identity | `PASS` | Production checkout, backend `/api/health`, frontend `/build-info.json`, `github/main`, candidate branch and canonical release marker all resolved to the live application SHA. |
| Authenticated functional Build smoke | `PASS` | Run `finn-v2-run-3a7697e21f084448aef1ff662fe79a41` completed `capability` with one dispatch and one attempt; the persisted typed terminal projection had initial/final operation `capability`, no tools and no proposal. |
| Latency observation | `RECORDED` | The functional smoke is not a statistical performance benchmark. |
| Independent production QA | `NOT_STARTED` | User-controlled; Build did not start or contact QA. |

## Functional Build Smoke

- Tested SHA: `5735c004fa6d0545ae852b2a795386ae647c48f0`.
- Run: `finn-v2-run-3a7697e21f084448aef1ff662fe79a41`.
- Terminal status: `completed`; initial/final operation: `capability`;
  canonical target: none.
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
- Asset selection, indicator configuration CRUD, setup/strategy deletion,
  non-live bot CRUD/deactivation, report reads and review-history reads now
  use existing V2 proposal or read boundaries. New write adapters are disabled
  by default and retain proposal, confirmation, idempotency and owner-scope
  checks. Legacy `generate_strategy` remains unavailable to new V2 runs.
- The action-contract candidate and its production migration repair are live.
  Independent QA is authorized by this status, but is not started by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
