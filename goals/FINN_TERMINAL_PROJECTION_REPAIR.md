# GOAL - FINN V2 terminal projection and degraded lineage repair

## Baseline

- Base commit: `eff6de71bbab29cccc0f3ebf32fe78fc4e0838dd`
- Branch: `codex/finn-terminal-projection-repair`
- Model configuration: unchanged (`gpt-4o-mini`)

## Objective

Repair the FINN V2 terminal contract so persisted, polling, SSE, and QA
operation views agree; preserve safe degraded lineage; and return
operation-specific safe responses for unavailable terminal contracts.

## In Scope

1. Persist compact terminal metadata for initial/final operation, allowed
   operation changes, target source, and conversation reference.
2. Preserve safe degraded EVALUATE lineage from the request-plan operation,
   even when the verified response is downgraded to `UNAVAILABLE`.
3. Deliver safe, operation-specific terminal responses for off-topic,
   unsupported financial operations, and policy-blocked bot activation.
4. Make EVALUATE without saved plan context return an honest bounded response
   with a concrete next step, without inventing evidence.
5. Add focused end-to-end regressions for persisted state, polling, SSE,
   lineage, terminal fallbacks, and QA operation extraction.

## Required Invariants

- Keep bounded polling and the one-time persisted terminal projection.
- Do not query the artifact chain per terminal poll.
- Keep polling and SSE envelopes identical.
- Preserve dispatch idempotency, asset precedence, no-write protections,
  confirmation gates, live-bot blocking, and release-marker behavior.
- Do not alter model configuration, selector prompts, registry semantics,
  datasets, thresholds, or sealed cases.
- Do not add prompt- or case-specific routing.

## Validation Gates

- Targeted terminal, lineage, fallback, EVALUATE, policy, dispatch, and SSE
  tests pass.
- Development, regression, and unchanged published holdout selector runs pass.
- Runtime coverage proves selector, persisted initial/final operation, polling,
  SSE, and QA extraction agree unless an explicit change reason exists.
- Root backend suite, relevant frontend/mobile checks, and `git diff --check`
  pass before release.

## Release Rule

- If any required build gate remains red: report `NOT READY FOR QA`; do not
  deploy or start QA.
- If every gate passes: commit one candidate, push, deploy through the normal
  workflow, verify SHA and health, and hand off exactly once to independent QA.
- Do not repair automatically after the QA verdict.
