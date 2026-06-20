# FINN Staging UI Telemetry Pass

Last updated: 2026-06-09

## Purpose

This pass is the final staging check for the FINN Product Sprint 1 telemetry layer.

What is already confirmed:

- prompt routing is stable on staging
- vague prompt latency is now fast
- decision-review boundary prompts route correctly
- prompt usage analytics are being recorded

What still needs explicit UI confirmation:

- `finn_overlay_opened`
- `report_ask_finn_used`
- confirm funnel events:
  - `finn_confirm_opened`
  - `finn_confirm_canceled`
  - `finn_confirm_confirmed`
- screen-level telemetry filling `top_screens`

## Baseline

- staging URL: [https://staging.tradamind.com](https://staging.tradamind.com)
- expected staging health:
  - [https://staging.tradamind.com/api/health](https://staging.tradamind.com/api/health) -> `200`
  - [https://staging.tradamind.com/report](https://staging.tradamind.com/report) -> `200`
  - [https://staging.tradamind.com/api/system/health](https://staging.tradamind.com/api/system/health) -> `401`
- current staging target:
  - commit `9ab4a75`

## Test sequence

Run the sequence in this order so the analytics output is easy to read.

### 1. Open FINN overlay from Setup

Route:

- `/setup`

Actions:

- load the Setup screen
- open the FINN overlay once
- do not ask a prompt yet

Expected telemetry:

- `screen_view` for `/setup`
- `finn_overlay_opened`
- `screen_view` for FINN overlay surface

## 2. Use report -> FINN

Route:

- `/report`

Actions:

- load the Report screen
- use the Finn Reports section
- trigger the Finn fetch once through the report flow

Expected telemetry:

- `screen_view` for `/report`
- `report_ask_finn_used`
- `report_finn_requested`

## 3. Confirm flow: open and cancel

Recommended surface:

- a safe FINN-driven confirm flow from setup or bot

Actions:

- open one confirm modal/sheet
- cancel it

Expected telemetry:

- `finn_confirm_opened`
- `finn_confirm_canceled`

## 4. Confirm flow: open and confirm

Recommended surface:

- another safe confirm path on setup/bot/strategy

Actions:

- open one confirm modal/sheet
- confirm it

Expected telemetry:

- `finn_confirm_opened`
- `finn_confirm_confirmed`

## 5. Optional operator signal fill

If time allows, add one real operator interaction:

- decision review from setup
- priority help from dashboard/portfolio

Expected telemetry:

- `decision_review_used`
- `priority_engine_used`

## Analytics readback

After the UI pass, inspect:

- local staging `/api/system/finn-analytics`

What should now be visible:

- `top_screens` is no longer empty
- `confirm_funnel` is no longer `0 / 0 / 0`
- `event_count` increases beyond prompt-only runs
- `decision_review_usage_count` and `priority_engine_usage_count` continue to move when those flows are used

## Pass criteria

This pass is successful when all of these are true:

- overlay open event is visible
- report -> FINN event is visible
- confirm open/cancel/confirm events are visible
- `top_screens` is populated
- no unexpected 4xx/5xx errors appear in the tested flows

## Suggested reporting format

Return results as:

1. flows completed
2. telemetry fields confirmed
3. analytics snapshot summary
4. anything missing or unexpectedly empty
