# FINN Product Sprint 1 – Staging Tester Checklist

Last updated: 2026-06-09

Environment:

- staging web: [https://staging.tradamind.com](https://staging.tradamind.com)
- staging backend analytics snapshot: `GET /api/system/finn-analytics` (operator-only)
- current staging commit: `ba9603e`

## Purpose

This checklist is meant to generate the first real internal-tester telemetry for FINN Product Sprint 1.

The goal is not broad exploratory QA.
The goal is to create clean early signal for:

- top FINN prompts
- top screens
- confirm open / confirm / cancel funnel
- Decision Review usage
- Priority Engine usage

## Before You Start

1. Log in on staging with your normal internal test account.
2. Use the product normally; do not hammer one button repeatedly.
3. Keep a short note of anything that feels unclear, stale, or too verbose.

## Core Flow 1 — Basic FINN usage

Do this:

1. Open FINN from the main interface.
2. Ask one general product/context question.
3. Ask one risk-oriented question.
4. Click one suggested next-best-action if FINN offers one.

Example prompts:

- `Wat is nu mijn belangrijkste aandachtspunt?`
- `Leg mijn huidige context kort uit.`
- `Waar zit nu het grootste risico?`

Expected telemetry:

- `screen_view`
- `finn_prompt_submitted`
- `finn_response_received`
- `next_best_action_clicked` (if used)

## Core Flow 2 — Setup review

Do this:

1. Open the Setup page.
2. Open a real setup.
3. Trigger a FINN review.
4. Ask a follow-up question from that setup context.

Example prompts:

- `Beoordeel deze setup voor mij.`
- `Past deze setup nog bij mijn plan?`

Expected telemetry:

- `screen_view` on setup
- `finn_prompt_submitted`
- `finn_response_received`
- `decision_review_used` when applicable

## Core Flow 3 — Report explanation

Do this:

1. Open the Report page.
2. Open the Finn report section or use the report explanation path.
3. Ask FINN to translate the report into action/risk context.

Example prompts:

- `Leg uit wat belangrijk is in dit rapport.`
- `Vat dit rapport samen in conclusie, risico en volgende stap.`

Expected telemetry:

- `screen_view` on report
- `report_finn_requested`
- `finn_prompt_submitted`
- `finn_response_received`

## Core Flow 4 — Portfolio / bot review

Do this:

1. Open the Bot / portfolio screen.
2. Ask FINN for a trade check or bot context explanation.
3. If a review path is shown, follow it once.

Example prompts:

- `Controleer deze botactie.`
- `Wat is hier het grootste uitvoeringsrisico?`

Expected telemetry:

- `screen_view` on bot/portfolio
- `finn_prompt_submitted`
- `finn_response_received`
- `decision_review_used` or `priority_engine_used` when applicable

## Core Flow 5 — Confirm funnel

Do this once in a real confirm flow:

1. Open a FINN-driven confirm or draft review.
2. Cancel one confirm.
3. Open another confirm.
4. Confirm it if the action is safe in staging.

Expected telemetry:

- `finn_confirm_opened`
- `finn_confirm_canceled`
- `finn_confirm_confirmed`

## Core Flow 6 — Priority / next-best-action signal

Do this:

1. Ask FINN what should be done next.
2. If Priority Engine or a next-best-action card appears, click one of them.

Example prompts:

- `Wat moet ik nu als eerste doen?`
- `Geef mijn prioriteiten voor vandaag.`

Expected telemetry:

- `priority_engine_used` when triggered
- `next_best_action_clicked`

## What Testers Should Watch For

Please note if any of these happen:

- FINN answer is too long before giving the conclusion
- risk framing is vague
- next step is missing or too generic
- confirm text is unclear
- loading state feels blank or untrustworthy
- empty state says too little
- error state feels technical instead of helpful

## Operator Readout After Testing

After several tester runs, inspect:

- local operator endpoint on staging:
  - `/api/system/finn-analytics`

Look for:

- `top_prompts`
- `top_screens`
- `confirm_funnel`
- `decision_review_usage_count`
- `priority_engine_usage_count`
- `repeated_user_signal`

## Exit Condition For This Pass

This first telemetry pass is useful once we have:

- multiple prompt types used
- multiple screens represented
- at least one confirm cancel
- at least one confirm success
- at least one Decision Review usage
- at least one Priority Engine usage
