# GOAL - FINN V1 runtime contract stabilization

## Baseline and scope

- Production baseline: `1329efe20a7c709fe83193695f98f176a1f48b1e`
- Branch: `codex/finn-v1-runtime-contract-stabilization`
- Goal: one canonical, versioned FINN runtime contract; one registry-governed
  transition authority; typed lineage and guided state; one persisted terminal
  projection consumed unchanged by polling, SSE, delivery, and QA.

## Non-goals

- No new user features, design work, model changes, broad runtime rewrite,
  prompt/case hardcoding, dataset or threshold changes, or deployment before
  every phase and final gate pass.

## Required phases

1. Freeze a machine-readable local corpus baseline with runtime projections,
   transitions, safety counts, and phase timings.
2. Introduce a versioned, run-bound `FinnRuntimeContract` with immutable intent
   and persisted lifecycle state.
3. Make the operation registry the sole validated transition authority.
4. Centralize canonical target resolution, including gold/XAU aliases.
5. Persist typed verified/degraded lineage and guided-flow state revisions.
6. Produce typed verifier terminal decisions and safe operation-specific output.
7. Materialize one hashed terminal projection for polling, SSE, delivery, and
   QA; instrument bounded runtime timings.

## Invariants

- Preserve one dispatch attempt, bounded polling, polling/SSE identity, compact
  terminal persistence, no V1 fallback, owner/asset isolation, no-write safety,
  proposal/confirmation/execution idempotency, non-live bot default, and the
  canonical atomic `LAST_GOOD_COMMIT` design.
- Initial intent and operation remain immutable. Any final transition must be
  registry-approved, typed, explicit, and provenance-preserving.
- Existing runs remain read-only readable through their original projection
  version.

## Gates

- Every phase has schema, serialization, persistence, replay, transition, and
  focused regression coverage before its successor.
- Final corpus: operation >=98%, independent holdout >=95%, target/polarity/
  write-input 100%, conversation reference >=95%, off-topic/unsupported 100%,
  transport projection identity 100%, single dispatch 100%, zero unauthorized
  writes/executions/infrastructure errors/500s/V1 fallbacks/data leaks.
- Runtime p95 <=10 seconds and hard maximum <=15 seconds.
- Root backend, relevant frontend/mobile, `git diff --check`, CI and governed
  production health checks must pass.

## Release rule

- Commit small reversible phases. Do not deploy or start QA while any phase or
  final gate is red.
- After one green candidate is deployed and SHA/health/markers agree, start
  exactly one independent read-only QA run and stop after its verdict. Never
  auto-repair after a QA verdict.
