# GOAL - FINN Runtime Contract Authority Foundation

## Scope

Make one persisted `FinnRuntimeContract` authoritative from FINN V2 run creation
through terminal delivery. The contract must be created before selector work,
carry immutable run/conversation/trace/user identity, use revision-checked typed
transitions, and materialize every new-run terminal projection.

## Baseline

- Production postmortem release: `c82a4d9c01d9ad4d6b4cd52b0340141bb3ee830c`
- Development base: `2440e098f94cbb375bccecc4424228da5a22d98a`
- Postmortem finding: the prior contract was terminal observer telemetry only.

## Required Foundation Work

1. Persist exactly one pending contract at run creation with run, conversation,
   trace and user identity, contract version and revision.
2. Make identity immutable and initial operation write-once after selection.
3. Provide revision-checked transitions for selector and terminal phases.
4. Make `complete_run` and `fail_run` transition the existing contract rather
   than construct a new contract.
5. Materialize typed projections for every new-run terminal status, including
   internal failures. `legacy_compact` is historical-read-only only.
6. Add minimal selector integration that writes initial operation and requested
   mode to the existing contract.

## Explicit Non-Goals

- No RequestPlan migration, resolver rewrite, target/lineage/guided-state
  migration, verifier/EVALUATE rewrite, bot semantic repair, latency work,
  runtime corpus gate, deployment, provider evaluations or QA handoff.

## Acceptance Evidence

- Tests prove pre-selector creation, immutable identity and operation,
  single-contract cardinality, transition revision checking, terminal updates
  for complete and failed runs, no new-run `legacy_compact`, historical read
  compatibility, polling/SSE projection equality, and worker-driven lifecycle
  use of one contract ID.
- Relevant existing tests and `git diff --check` pass.
- No production or QA action is taken.

## Stop Rule

Stop after one Foundation candidate and report the remaining Goal 2 work. Do
not begin any excluded migration or release step.
