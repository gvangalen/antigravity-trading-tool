# FINN Operator 90+ Sprint

Last updated: 2026-06-09

## Purpose

This sprint is the direct follow-up to the current FINN certification baseline:

- Core: `90`
- Operator: `85`
- Performance Intelligence: `91`
- Governance: `91`

The goal is simple:

- move **Operator** from `85` to `90+`
- do it through product-quality depth, not by inventing a new FINN layer
- use real staging/live telemetry to guide the fixes

This is not a rescue sprint.
This is a targeted quality-elevation sprint.

## Current reading

What is already true:

- full Core + Operator confirm run is green on live
- replay gate is clean
- latency on the confirm path is healthy
- the remaining combined-stack gap is mainly Operator quality depth

What this means:

- we do **not** need large routing or safety work first
- we do **not** need another platform-scale sprint first
- we need sharper Operator behavior on the main decision/support flows

## Sprint goal

Raise Operator from `85` to `90+` by improving:

1. prompt handling quality
2. coaching sharpness
3. review/decision framing
4. next-best-action usefulness
5. follow-through consistency after decisions

## Success criteria

The sprint is successful when all of these are true:

- Operator score reaches `90+`
- no Operator category drops below `85`
- no increase in generic failures
- no increase in transactional misroutes
- next-best-actions are noticeably more specific and less boilerplate in QA review
- telemetry shows meaningful usage of:
  - Decision Review
  - Priority Engine
  - confirm flows
  - report explanation

## Priority order

### Workstream 1 — Operator prompt quality

Focus:

- tighten how FINN handles operator-style prompts around:
  - what should I do now
  - what is blocked
  - what should I review first
  - what changed after this action
  - what is the safest next step

Target outcome:

- less generic assistance
- more concrete operational guidance
- less repeated “safe but vague” language

Primary touchpoints:

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

### Workstream 2 — Decision/review framing

Focus:

- make Operator responses more consistent on:
  - conclusion
  - risk framing
  - what changed
  - exactly one next step

Target outcome:

- decision responses read more like operator guidance and less like descriptive commentary

Primary touchpoints:

- [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx)
- [mobile/src/screens/FinnScreen.tsx](/Users/gvangalen/Documents/antigravity-trading-tool/mobile/src/screens/FinnScreen.tsx)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

### Workstream 3 — Next-best-action usefulness

Focus:

- reduce generic next steps
- prefer explicit next actions tied to:
  - setup
  - bot
  - report
  - portfolio risk
  - confirm follow-through

Target outcome:

- next-best-action clicks become a useful product signal instead of just decorative UI

Primary touchpoints:

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx)
- [mobile/src/services/dataMappers.ts](/Users/gvangalen/Documents/antigravity-trading-tool/mobile/src/services/dataMappers.ts)

### Workstream 4 — Telemetry-driven tuning

Focus:

- use the new FINN Product Sprint 1 analytics to inspect:
  - top prompts
  - top screens
  - confirm funnel
  - Decision Review usage
  - Priority Engine usage

Target outcome:

- Operator improvements are based on real usage, not only prompt intuition

Primary references:

- [docs/operations/finn-product-sprint-1.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-product-sprint-1.md)
- [docs/operations/finn-product-sprint-1-staging-tester-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-product-sprint-1-staging-tester-checklist.md)

## QA approach

Release lane stays:

1. local
2. staging
3. internal tester run
4. operator QA
5. live confirm run

### Required checks

- replay promptsets for Core + Operator
- targeted Operator rerun on:
  - decision review
  - priority guidance
  - report explain
  - follow-through after confirm
- inspect `/api/system/finn-analytics` on staging after tester traffic

## What not to do

Do not turn this sprint into:

- FINN 6.0 discovery
- new agent architecture
- new dashboard families
- broad UI redesign
- another synthetic scale sprint

## Exit condition

We can close this sprint when:

- Operator is `90+`
- the prompt/decision/follow-through layers feel sharper in replay review
- telemetry confirms people actually use the improved flows
- the remaining work is no longer about Operator depth, but about ongoing product iteration

## Follow-up after the decision-review variant pass

After the staging variant family reached `15/15 passed`, the remaining finishing work is tracked in:

- [docs/operations/finn-operator-follow-up-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-operator-follow-up-checklist.md)

That checklist covers:

- rescue/general-help latency polish
- the product choice for ultra-implicit review prompts
- one more slang/indirect boundary pass
- a real UI telemetry fill pass for `top_screens` and the confirm funnel
