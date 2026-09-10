# GOAL - FINN 1507 Production QA Repair

## Scope

Repair the shared runtime defects reported by the one official QA run on
production SHA `1507b3d4e5affdefeb4a17aa059821007a07caba`:

- owner-scoped action-result lineage across independent runs;
- typed previous-response lineage for evidence follow-up and reformulation;
- bounded terminal read/evaluate behavior for linked bots and plans;
- registry-consistent `evaluate_bot` and `update_strategy` selection.

## Non-goals

- Do not read, copy, modify, or score the QA-exclusive sealed manifest.
- Do not add action contracts, lower gates, add prompt-specific exceptions, or
  change safety, confirmation, broker, or live-bot policy.
- Do not deploy or start official QA until the full local repair batch passes.

## Required evidence

Use only the reported run IDs, sanitized runtime traces, non-sealed local
fixtures, and existing canonical action contracts. Reproduce the full natural
create -> resolve -> update -> dependent create -> delete chain from one fresh
owner without injected object IDs in user messages.

## Acceptance gates

- all 16 natural write contracts pass locally through proposal, confirmation,
  execution, idempotent replay, terminal projection, polling, and SSE;
- the 9 dependent object resolutions use prior execution result or a unique
  owner-scoped canonical object, never cross-user or arbitrary matching;
- linked-bot read, plan evaluation, evidence follow-up, reformulation,
  bot-consequence, and strategy update terminalize under their registry
  contract;
- full backend suite and real-provider development/regression pass;
- no unauthorized write, broker order, live trade, or live-bot activation.

## Release rule

Create one candidate only after all gates pass. Deployment and independent QA
require a separate explicit user release instruction.
