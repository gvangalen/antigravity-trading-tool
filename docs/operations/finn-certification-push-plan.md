# FINN Certification Push Plan

Last updated: 2026-06-04

## Purpose

This document defines the smallest high-ROI push needed to move FINN from:

- stable and product-credible

to:

- broadly certification-ready across the active QA layers

It is intentionally narrow.
The goal is not to invent FINN 6.0 work.
The goal is to close the remaining certification gaps with the least risky tranche.

## Current Certification Snapshot

Best current references:

- Core: `90`
- Operator: `85`
- Performance Intelligence: `91`
- Governance: `91`

Interpretation:

- 4.0 Performance Intelligence is strong
- 5.0 Governance is strong
- Core has now crossed the `90` bar on the latest full run
- the broad certification bottleneck is now concentrated in:
  - Operator `85 -> 90+`
  - latency polish where strict replay gates still care
  - QA/rubric alignment where governance correctly takes over the riskiest operator prompts

## Main Decision

Do not broaden feature scope first.

Run one focused certification push across:

1. Operator
2. latency-only replay polish where still needed
3. QA/rubric alignment for governance overlap

This is the shortest route to a cleaner overall FINN status.

## Priority Order

### P0 — Operator 85 -> 90+

Operator is now stable, but not yet broad-certification strong.

Likely remaining point leaks:

- decision review can still be a bit conservative in some cases
- priority answers can still be sharper and less repetitive
- some legacy operator expectations still classify governance takeover as a fail even when the product got safer

Target outcomes:

- operator categories move from mid-80s toward `90`
- no regression in governance or performance layers

Likely touchpoints:

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

### P1 — Governance latency polish

Governance is already content-green.

The only remaining 5.0 nuance is:

- strict replay latency budget polish on the heaviest prompts

This should remain a polish stream, not a major product stream.

Target outcomes:

- formal governance replay gate also trends green
- no content regressions

## Workstreams

## Workstream A — Operator Sharpness

Focus:

- richer decision-review language when enough scenario data exists
- priority outputs more differentiated by question type
- less “correct but flat” operator messaging

Acceptance:

- Operator reaches `90+`
- no category below `80`

## Workstream B — Replay Latency Hygiene

Focus:

- heaviest governance and explain prompts
- read-only fast-paths where safe
- smaller response construction where possible

Acceptance:

- fewer budget overruns
- no regression in intent quality

## Workstream C — QA / Rubric Alignment

Focus:

- treat `governed_action_review` as valid on safety-sensitive portfolio permission prompts
- keep old operator prompts useful without pretending the architecture never evolved
- avoid false-negative certification reports caused by valid governance takeover

Acceptance:

- promptsets and rubrics reflect current lane ownership
- future certification runs do not count safer governance behavior as an operator failure

## What Not To Do In This Push

Do not:

- add new major FINN product phases
- introduce autonomous execution expansion
- redesign frontend surfaces broadly
- rewrite working 4.0 or 5.0 engines just to chase style points

This push is about finishing, not expanding.

## Recommended Execution Sequence

1. Operator sharpness tranche
2. replay latency polish tranche
3. QA / rubric alignment tranche
4. rerun:
   - full Core/Operator QA
   - dedicated 4.0 QA
   - dedicated 5.0 QA
5. refresh certification summary

## Definition Of Done

This push is done when:

- Core is `90+`
- Operator is `90+` or very near with no category below `80`
- Performance Intelligence remains `90+`
- Governance remains `90+`
- replay artifacts are clean enough to call the system broadly certification-ready
- QA promptsets no longer penalize valid governance takeover on high-risk prompts

## Practical Next Step

Start with the **Operator sharpness + rubric alignment tranche**.

Reason:

- Core is already over the line on the latest full run
- the remaining blocker is mostly Operator depth plus rubric alignment
- this is the smallest next step that improves the certification story without broadening scope
