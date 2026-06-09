# Tradamind FINN Product Sprint 1

Last updated: 2026-06-08

## Purpose

This sprint shifts Tradamind back from platform hardening and UI polish toward product value.

The focus is deliberately narrow:

- improve FINN on the main chat/review surfaces
- turn on lean real-user telemetry
- make primary FINN surfaces feel production-grade during loading, empty, and error states
- keep staging-first release discipline explicit

This is not a FINN 6.0 sprint and it does not introduce a new agent family.

## Scope

### 1. FINN response contract

Primary FINN chat/review paths now normalize these top-level fields when available:

- `summary`
- `risk_summary`
- `next_best_action`
- `review_reason`

The contract is additive, not breaking.
Existing consumers can continue to read the older envelope shape, while newer surfaces can rely on consistent summary/risk/next-step framing.

### 2. Lean product analytics

The sprint uses a local backend event path instead of a large third-party analytics dependency.

Current ingest endpoint:

- `POST /api/assistant/analytics/events`

Current operator snapshot endpoint:

- `GET /api/system/finn-analytics`

Tracked first-wave events:

- `finn_prompt_submitted`
- `finn_response_received`
- `finn_confirm_opened`
- `finn_confirm_confirmed`
- `finn_confirm_canceled`
- `screen_view`
- `report_finn_requested`
- `decision_review_used`
- `priority_engine_used`
- `next_best_action_clicked`

Required event shape:

- `event_name`
- `user_id` (server-side)
- `session_id`
- `surface`
- `page`
- `asset`
- `flow_type`
- `timestamp`

Optional fields already supported:

- `action_type`
- `report_type`
- `decision_id`
- `bot_id`
- `setup_id`
- `strategy_id`
- `trace_id`
- `prompt_text`
- `next_best_action`
- `metadata`

Current analytics scope:

- process-lifetime snapshot
- early-tester directional signal
- not yet a durable warehouse or BI pipeline

## Product-quality pass

Primary surfaces for this sprint:

- setup
- report
- FINN overlay/panel
- portfolio bot/trade review
- watchlist -> FINN handoff

Expectations:

- loading states explain what is happening
- empty states explain why that can be normal
- error states explain what failed and what the user can do next
- raw technical messages are not the main user experience

## Release discipline

This sprint assumes the new environment split is now mandatory:

1. local
2. staging (`develop` -> staging host)
3. core QA
4. operator QA
5. performance QA
6. governance QA
7. production (`main` -> production host)

No direct production-only deploy path should be used for FINN product work.

## Monitoring inventory

Chosen current path per category:

- uptime monitoring:
  - public health checks on staging and production
  - `/api/health`
  - `/report`
- backend error visibility:
  - PM2 logs
  - backend application logs
  - operator review during staging-first rollout
- queue health visibility:
  - `/api/system/health`
  - queue depth and worker visibility from deep health
- database health visibility:
  - backend deep health DB status
  - deploy-time smoke checks
- release marker visibility:
  - `repo_head`
  - `production_head`
  - `LAST_GOOD_COMMIT`
  - release rehearsal and status docs
- FINN product analytics:
  - `/api/system/finn-analytics`

## Acceptance

This sprint is considered successful when:

- FINN main chat/review flows consistently expose conclusion + risk + next step
- operators can inspect top prompts, top screens, confirm funnel behavior, Decision Review usage, and Priority Engine usage
- setup/report/portfolio/FINN/watchlist surfaces no longer rely on generic loading or empty/error placeholders
- staging-first release discipline stays intact
