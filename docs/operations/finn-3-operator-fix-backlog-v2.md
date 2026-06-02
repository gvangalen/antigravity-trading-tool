# FINN 3.0 Operator Fix Backlog V2

## Summary

This backlog defines the next targeted operator tranche after the live QA run on `aac2157`.

Current live baseline:

- Core score: `86`
- Operator score: `60`

Current operator category scores:

- Decision Review: `62`
- Plan Adherence: `82`
- Outcome Tracking: `74`
- Portfolio Intelligence: `56`
- Priority Engine: `28`

This tranche is intentionally narrow.

We are **not** broadening FINN 3.0 again.
We are fixing the three operator gaps that still prevent FINN from feeling like a consistent operator layer:

1. `priority_engine`
2. `portfolio_intelligence`
3. `decision_review`

Plan Adherence and Outcome Tracking are no longer the main problem in this slice.
They should be protected from regression, but they are not the primary build target.

---

## P0 Goals

### 1. Priority Engine must stop falling back to `general_help`

Direct priority and focus prompts should route to `priority_engine` by default when the user is clearly asking:

- what should I do first
- what matters most today
- what can wait
- where should I focus now

### 2. Portfolio Intelligence must consistently win on exposure and concentration prompts

Portfolio prompts should stop falling back to:

- `general_help`
- `plan_creation`

when the user is clearly asking about:

- exposure concentration
- stacked risk
- adding more BTC risk
- portfolio-level blockers

### 3. Decision Review must become the default trade-review lane

Trade-review prompts should stop drifting into broad help or partial portfolio analysis when the user is clearly asking:

- should I do this
- review this trade
- would you take this trade
- why are you blocking this trade

---

## Category 1 - Priority Engine

### Problem

Priority Engine is still the weakest operator surface.
In the latest run it improved from `18` to `28`, but most direct priority prompts still routed to `general_help`.

### Observed failures

Examples that still need to land on `priority_engine`:

- `Wat is vandaag mijn hoogste prioriteit?`
- `Wat moet ik nu eerst doen?`
- `Waar moet ik vandaag op focussen?`
- `Wat kan vandaag wachten?`

### Likely root cause

- Priority detection is still too literal
- Mission Control summary content exists, but free-form priority prompts do not consistently reuse the same lane
- fallback precedence still allows broad help language to win

### Touchpoints

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

Likely focus areas:

- `looks_like_priority_engine_request(...)`
- route precedence near Mission Control and general help handling
- rescue envelope logic for read-only prompts
- normalization of focus / sequence / defer language

### Required behavior

Priority prompts must resolve to:

- `intent = priority_engine`

Expected response contract:

- `headline`
- `top_priorities`
- `review_queue`
- `ignore_today`
- `why_now`

The first response should answer:

- what to do now
- why now
- what can wait

### Acceptance criteria

- all direct priority prompts route to `priority_engine`
- none of those prompts route to `general_help`
- Mission Control style priority language is reused in the answer
- replay gate includes at least 4 explicit priority prompts

---

## Category 2 - Portfolio Intelligence

### Problem

Portfolio Intelligence is materially better than the first operator baseline, but still too unstable.
The content is often useful, but routing still leaks to the wrong lane.

### Observed failures

Examples that still need to land on `portfolio_intelligence`:

- `Ik heb 70% BTC exposure, kan ik nog een BTC long openen?`
- `Voeg ik nu te veel geconcentreerd risico toe?`
- `Wat is mijn grootste portfolio risico?`
- `Mag ik extra BTC risico toevoegen?`

### Likely root cause

- exposure and concentration terms still compete too often with generic help
- some prompts are interpreted as planning or strategy construction instead of portfolio evaluation
- decision review and portfolio review are not yet normalized as complementary lanes

### Touchpoints

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

Likely focus areas:

- `looks_like_portfolio_intelligence_request(...)`
- allocation / concentration / correlation phrase coverage
- precedence versus `plan_creation`
- precedence versus `general_help`
- portfolio layer reuse inside `decision_review`

### Required behavior

Portfolio prompts must resolve to:

- `intent = portfolio_intelligence`

or, if the prompt is clearly trade-review shaped:

- `intent = decision_review`
- with a populated portfolio layer in analysis

Expected response contract:

- `portfolio_impact`
- `exposure_delta`
- `concentration_warning`
- `stacked_risk_warning`
- `portfolio_blockers`
- `portfolio_safe_alternative`

### Acceptance criteria

- exposure/concentration prompts no longer route to `general_help`
- exposure/concentration prompts no longer route to `plan_creation`
- BTC-heavy allocation prompts explicitly mention concentration risk
- trade-review prompts with portfolio language either:
  - route to `portfolio_intelligence`, or
  - route to `decision_review` with clear portfolio blockers

---

## Category 3 - Decision Review

### Problem

Decision Review is improving, but it still does not own trade-review intent strongly enough.
The content can be useful, but the lane is not yet stable.

### Observed failures

Examples that still need to land on `decision_review`:

- `Controleer deze trade voor mij`
- `Moet ik deze trade openen?`
- `Zou jij dit doen?`
- `Waarom blokkeer je deze trade?`

### Likely root cause

- review detection still over-relies on explicit review verbs
- natural prompts like `Zou jij dit doen?` are too ambiguous and drift to `general_help`
- decision review, behavioral guidance, and portfolio review still overlap without a hard tie-break

### Touchpoints

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

Likely focus areas:

- `looks_like_decision_review_request(...)`
- trade-intent normalization
- precedence versus `general_help`
- precedence versus `portfolio_intelligence`
- response contract filling for review-specific prompts

### Required behavior

Trade-review prompts must resolve to:

- `intent = decision_review`

Expected response contract:

- `review_type`
- `decision_status`
- `checks`
- `top_blockers`
- `recommended_changes`
- `risk_summary`
- `operator_next_step`

### Acceptance criteria

- natural trade-review prompts route to `decision_review`
- `Zou jij dit doen?` no longer falls back to `general_help` when trade context is clear
- review answers explicitly state:
  - approve / modify / block / insufficient_context
  - why
  - what to do next

---

## Protection Goals

The following categories must stay stable while we fix the remaining operator gaps:

- Plan Adherence
- Outcome Tracking
- Core coaching behavior
- Core reliability

Regression rule:

- no degradation of the current live operator wins on:
  - `Mijn plan zegt wachten maar ik wil kopen`
  - `Ik wil mijn stop-loss verwijderen`
  - explicit FOMO history prompts

---

## Implementation Order

### Tranche order

1. Priority Engine hardening
2. Portfolio Intelligence hardening
3. Decision Review normalization
4. replay gate expansion
5. full FINN 3.0 operator QA rerun

### Why this order

- Priority Engine is the weakest category and the clearest routing miss
- Portfolio Intelligence already has useful content and should yield quickly with better precedence
- Decision Review benefits from the portfolio normalization and can then claim its own lane more cleanly

---

## Test Plan

### Service tests

Extend:

- [backend/trading-tool-backend/backend/tests/test_finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_finn_plan_service.py)
- [backend/trading-tool-backend/backend/tests/test_ai_assistant_api_unified_core.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_ai_assistant_api_unified_core.py)

Add targeted cases for:

- `Wat is vandaag mijn hoogste prioriteit?`
- `Wat moet ik nu eerst doen?`
- `Wat kan vandaag wachten?`
- `Ik heb 70% BTC exposure, kan ik nog een BTC long openen?`
- `Voeg ik nu te veel geconcentreerd risico toe?`
- `Controleer deze trade voor mij`
- `Moet ik deze trade openen?`
- `Zou jij dit doen?`

### Replay gate

Extend:

- [backend/trading-tool-backend/backend/tests/test_finn_qa_replay_gate.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_finn_qa_replay_gate.py)
- [docs/operations/finn-qa-promptset-full.json](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json)

Add assertions for:

- direct priority prompts -> `priority_engine`
- concentration prompts -> `portfolio_intelligence`
- natural trade-review prompts -> `decision_review`
- no fallback to `general_help` on those P0 prompt families

---

## Success Criteria

This tranche is successful when:

- Priority Engine becomes a real lane instead of an occasional hit
- Portfolio Intelligence stops drifting into `general_help` and `plan_creation`
- Decision Review becomes the default trade-review surface
- Plan Adherence stays strong
- Outcome Tracking stays strong
- Core remains at or above the current baseline

### Target outcome

We do not need operator certification in one jump.
The next goal is:

- Priority Engine clearly above its current `28`
- Portfolio Intelligence clearly above its current `56`
- Decision Review clearly above its current `62`
- overall Operator score materially above `60`

That would turn the current operator layer from "promising but uneven" into "consistently useful".
