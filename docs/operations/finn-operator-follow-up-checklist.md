# FINN Operator Follow-up Checklist

Last updated: 2026-06-09

## Purpose

This checklist captures the remaining high-ROI follow-up after the staging decision-review variant run on commit `08eceb3`.

What is already true:

- decision-review variant family is now green on staging: `15/15 passed`
- no transactional misroutes were seen in the variant run
- decision-review telemetry is filling correctly

What remains:

- ultra-vague `general_help` prompts are still slower than they should feel
- the line between implicit review and general help should be a conscious product choice
- screen-level telemetry still needs a real UI pass

This is not a new sprint.
It is a short finishing pass.

## P0 — Rescue/general-help latency polish

### Goal

Keep vague prompts in the `general_help` lane if needed, but make them feel light and fast.

### Focus prompts

- `Doe ik dit goed?`
- `Hmm, en deze dan?`

### Why this matters

- the current routing is acceptable
- the current latency is not
- this is a first-touch UX problem, not a correctness problem

### Likely touchpoints

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

### Implementation checklist

- add an explicit lightweight rescue/help branch for ultra-short reflective prompts
- avoid heavy context-building when the prompt has no strong entity anchor
- prefer compact read-only response generation over deeper explain/review scaffolding
- preserve telemetry so these prompts still show up in prompt analytics

### Validation

- replay the two focus prompts locally and on staging
- confirm they still route to the intended lane
- compare latency before/after
- ensure no new generic failure classification appears

## P1 — Product choice for ultra-implicit review prompts

### Goal

Make an explicit choice for prompts that sit between review and general help instead of letting them drift there by accident.

### Example prompts

- `Doe ik dit goed?`
- `Hmm, en deze dan?`
- `Is deze te doen?`
- `Voelt dit goed genoeg?`
- `Is dit nog oké?`

### Decision to make

Choose one of these two behaviors and keep it consistent:

1. treat them as `general_help` unless there is stronger context
2. treat them as lightweight `decision_review` when there is strong setup/strategy/bot context

### Likely touchpoints

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/tests/test_finn_product_sprint1.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_finn_product_sprint1.py)
- [docs/operations/finn-operator-90-plus-qa-handoff.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-operator-90-plus-qa-handoff.md)

### Implementation checklist

- define the preferred routing rule in code comments or helper naming
- add tests for the chosen behavior on at least 5 ultra-implicit prompts
- avoid widening the decision-review classifier so much that general rescue prompts get swallowed

### Validation

- rerun a small prompt family set on staging
- verify no regression on the current `15/15` decision-review family

## P1 — One more slang/indirect boundary pass

### Goal

Probe the semantic edge of the decision-review capture without making the classifier clumsy.

### Suggested test set

- `Is deze te doen?`
- `Voelt dit goed genoeg?`
- `Zou jij hier instappen?`
- `Is dit nog oké?`
- `Is deze entry het waard?`

### Likely touchpoints

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/tests/test_finn_product_sprint1.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_finn_product_sprint1.py)

### Validation

- keep this set separate from the core decision-review family
- classify outcomes as:
  - acceptable `general_help`
  - desirable `decision_review`
  - unacceptable misroute

## P2 — Real UI telemetry pass

### Goal

Fill the analytics fields that API replay cannot populate well enough.

### Signals still underrepresented

- `top_screens`
- `confirm_funnel`

### Real tester flows needed

- open FINN overlay from setup
- open FINN from report
- open a confirm flow and cancel it
- open a confirm flow and complete it
- use Decision Review from a real screen
- use Priority Engine from a real screen

### Likely touchpoints

- [docs/operations/finn-product-sprint-1-staging-tester-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-product-sprint-1-staging-tester-checklist.md)
- [frontend/trading-tool-frontend/lib/api/assistantAnalytics.js](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/lib/api/assistantAnalytics.js)
- [mobile/src/services/assistantAnalytics.ts](/Users/gvangalen/Documents/antigravity-trading-tool/mobile/src/services/assistantAnalytics.ts)

### Validation

- inspect `/api/system/finn-analytics` after real UI traffic
- confirm:
  - screen views populate
  - confirm funnel moves off `0/0/0`
  - decision review and priority usage continue to increment

## Recommended order

1. rescue/general-help latency polish
2. explicit product choice for ultra-implicit prompts
3. one small slang/indirect boundary pass
4. real UI telemetry pass

## Exit condition

This follow-up is done when:

- vague `general_help` prompts no longer feel slow
- the implicit-review boundary is intentional and tested
- no regression appears in the `15/15` decision-review family
- staging analytics includes real screen and confirm-funnel data
