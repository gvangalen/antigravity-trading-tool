# Tradamind – FINN Operator 90+ QA Handoff

## Baseline

- environment: `staging`
- url: `https://staging.tradamind.com`
- branch: `develop`
- commit: `2fe5b49`
- focus: `Workstream 1 + 2`
  - operator prompt quality
  - decision / review framing

## Goal

Validate that FINN now behaves more like a reliable operator layer on the main help, explain and review paths:

- shorter and clearer top-line conclusion
- explicit risk framing
- one useful next-best-action
- clearer distinction between:
  - explain
  - review
  - follow-through

This QA pass is **not** for new FINN features or platform scale.

## Primary Surfaces

Test these first:

1. `Report`
2. `Setup`
3. `Bot`
4. FINN overlay / side panel
5. mobile FINN feed if available in the current QA lane

## Core Prompt Set

### A. General help / operator capability

Surface:
- open FINN from `Setup` or `Report`

Prompts:
- `Wat kan Finn hier voor mij doen?`
- `Waar help je me hier het meest mee?`
- `Wat is hier eerst begrijpen en wat is pas een actie?`

Expected:
- clear operator help framing
- no vague “ik kan van alles” answer
- response should include:
  - what FINN can help with here
  - risk/read-only framing
  - one next step
- UI should show operator readout, not just plain prose

### B. Context explain

Surface:
- `Setup`
- `Report`
- `Bot`

Prompts:
- `Leg deze setup kort uit`
- `Wat betekent dit rapport nu voor mij?`
- `Waarom bestaat deze bot en waar wacht hij nu op?`
- `Wat zegt Mission Control hier nu in het kort?`

Expected:
- answer should feel screen-aware
- should not drift into generic coaching
- should explicitly tell the operator:
  - what this thing is
  - what the current risk or constraint is
  - what the next useful step is

Look for:
- better `summary`
- usable `risk_summary`
- concrete `next_best_action`
- visible operator readout card on web

### C. Decision review

Surface:
- `Setup`
- `Bot`
- any flow where a trade/setup/strategy review is natural

Prompts:
- `Beoordeel deze trade voor BTC met 3% risico`
- `Past deze setup nu bij mijn strategie?`
- `Zou jij dit nu openen?`
- `Review deze botbeslissing`

Expected:
- clear verdict
- clearer “why now”
- one next step only
- no vague descriptive wall of text
- decision review card should now show:
  - conclusion
  - risk
  - why now
  - next step

Important:
- if FINN blocks or modifies, the response should still feel actionable, not just negative

### D. Plan adherence

Surface:
- `Setup`
- `Bot`

Prompts:
- `Mijn plan zegt wachten maar ik wil toch kopen`
- `Ik wil mijn positie vergroten`
- `Mag ik dit toch doen ook al wijkt het af van mijn plan?`

Expected:
- explicit plan-friction framing
- strong but calm operator tone
- visible recovery step
- better distinction between:
  - in plan
  - insufficiently justified
  - forced override

## UI / Framing Checks

### Web

Check that assistant messages now present better framing:

- operator readout appears on explain/help-style answers
- decision review card includes:
  - clearer conclusion
  - why now
  - next step
- plan adherence card feels more like a decision guardrail than a generic explanation

### Mobile

Check that mobile FINN feed now carries the same conceptual contract:

- not only raw message text
- operator-style framing should be visible in the message card
- risk and next-step blocks should feel consistent with web even if visually lighter

## Telemetry / System Checks

After a short manual run, inspect:

- local operator endpoint on staging:
  - `/api/system/finn-analytics`

Useful signals to confirm:
- `finn_prompt_submitted`
- `finn_response_received`
- `decision_review_used`
- `priority_engine_used` when applicable
- `next_best_action_clicked` if follow-ups are tapped

This pass does not need big volumes. We mainly want proof that the new operator flows are visible in telemetry and can be inspected later.

## Pass Criteria

Mark this tranche as good if:

1. general help feels sharper and more bounded
2. explain responses are more screen-aware and operator-useful
3. decision review gives:
   - conclusion
   - risk
   - why now
   - one next step
4. plan adherence feels stronger and more disciplined
5. web and mobile both reflect the same contract idea
6. no regressions on:
   - `/api/health`
   - `/report`
   - FINN overlay opening
   - assistant response rendering

## Failure Patterns To Watch For

- answer is still too generic
- answer is descriptive but not actionable
- risk framing missing
- multiple competing next steps
- explain/review/confirm boundaries feel blurred
- operator readout missing on the web paths that should now have it
- mobile only shows flat text while web shows the richer contract

## Suggested QA Summary Format

Please return:

### A. What improved

### B. What still feels weak

### C. Whether Operator feels closer to `90+`

### D. Any prompt(s) that still underperform
