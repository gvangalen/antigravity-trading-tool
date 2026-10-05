# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Let users add optional text about how they want to trade and make it available as owner-scoped coaching context for FINN. |
| Candidate branch | `codex/finn-trader-context` |
| Candidate implementation SHA | `01b5fa0f9b638a150200e7085845a448f6d2816c`; this status commit follows it. |
| PR | [#75](https://github.com/gvangalen/antigravity-trading-tool/pull/75), merged. |
| Production SHA | `ecb0c9f0aa8bd794eebbfb45bc561246fd5dad16`; public backend and frontend both reported it with HTTP 200 on 2026-10-05. This status-only follow-up creates a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-05 |

## Change And Limits

- Onboarding and Mijn profiel now offer one optional, 1,000-character trader-context field. It persists under the authenticated user's existing `users.ai_preferences.trader_context`; no database migration is needed.
- The owner-scoped `read_profile` tool exposes the note as a separate typed field. FINN can use it for coaching while keeping it distinct from structured profile choices, verified plan rules, account balances and market facts.
- A profile with only free text is marked as user context only; it does not establish a structured trading style or risk tolerance. The text is not included in the compact profile summary.
- Local real Responses testing saved the note through the API, read it back, received a FINN answer quoting the saved note, then cleared the field and verified the empty value. This is local evidence, not authenticated production acceptance.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Owner-scoped profile runtime | Authenticated local save/read/clear returned HTTP 200; FINN quoted the stored note and did not infer unset style or risk fields. | `.local-finn-parity-artifacts/trader-context-probe.json`, SHA-256 `943e9a1881702191331310b5d1e81f75d4d397e63cd5824545a5c519c12b5f34`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/trader-context-action-matrix.json`, SHA-256 `8893e42f94ef30c5046f4f138416a46f18d0b22cdf297e132964ce2d01140e1e`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/trader-context-selector-development.json`, SHA-256 `677ddfcb6bfb1a82ec45c3c96c779cda8ac9f7c0c21b7242f83a4be72e00e5ef`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/trader-context-selector-regression.json`, SHA-256 `a3f36f7325ecba17e92da48f241abb09b103e7f214aa9c4eb38f2ea5854f6b52`. |
| Backend | `3100 passed, 3 skipped`; includes field bound, typed read, and context semantics. | `pytest -q`; `.local-finn-parity-artifacts/trader-context-pytest-final.log`. |
| Frontend | Typecheck, i18n lint and tests, command/proposal/setup tests, build and high-severity audit passed; zero high production dependency vulnerabilities. | `.local-finn-parity-artifacts/trader-context-frontend.log` and `trader-context-frontend-full.log`. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37300298893](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37300298893), all five jobs green. |
| Main CI and Auto Deploy | `PASS`: [main CI 37300525582](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37300525582) and [Auto Deploy 37300701292](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37300701292) on `ecb0c9f0aa8bd794eebbfb45bc561246fd5dad16`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `ecb0c9f0aa8bd794eebbfb45bc561246fd5dad16`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
