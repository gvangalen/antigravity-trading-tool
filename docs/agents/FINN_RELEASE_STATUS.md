# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Correct the saved weekly DCA weekday display and read the linked strategy when explaining one named saved DCA plan. |
| Candidate branch | `codex/finn-dca-weekday-readback` |
| Candidate implementation SHA | `e04e0f84`; followed by this release-status commit. |
| PR | [#67](https://github.com/gvangalen/antigravity-trading-tool/pull/67), merged. |
| Production SHA | `d32b433a6499d9779e837a5188a4597b6d71abe3`; public backend and frontend both reported it with HTTP 200 on 2026-10-04. This status-only follow-up creates a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- Authenticated live QA on `a2c2411d...` saved a fixed ETH DCA for Friday. The stored weekday was `5`, but the setup editor expected a weekday name and therefore showed Monday after refresh. The editor now maps ISO weekday codes to its choices and rejects an unknown saved code instead of silently presenting Monday. The saved inventory also exposes a weekday name alongside the raw code.
- For the exact saved Smart-DCA question supplied by the user, the production read trace selected `get_saved_setup_inventory` in `answer_mode=explain`. That route returned the named setup but did not read its linked strategy, so the model could not verify the saved €90 base and 70/100/130% curve. The inventory route now loads linked strategy evidence for an explanation of one selected DCA plan. It does not replace the model's answer.
- A six-run local real-model probe of that exact follow-up selected `get_active_plan_and_strategy` every time and read the saved curve in all six runs. A forced inventory-path regression covers the different route observed live. This is Build evidence, not authenticated production acceptance.
- Build used synthetic local users for writes and read-only production diagnostics. It did not access protected QA fixtures or the sealed holdout.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector evaluation gate used its configured `gpt-4o-mini`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact saved Smart-DCA question, six real-model conversations | `6/6` read the linked strategy and answered the €117 planned amount; all six selected the direct combined read. | `.local-finn-parity-artifacts/dca-saved-readback-variation.json`, SHA-256 `c01b03cd540d494036d4b3f144dee208190586c643cd3962abf54b5f4faa24c9`. |
| Forced inventory path | Exact user prompt; owner-scoped inventory followed by linked setup/strategy read. | `test_single_saved_dca_explanation_reads_strategy_even_when_model_chooses_inventory`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/dca-weekday-readback-action-matrix.json`, SHA-256 `08c8cbd300d3f85a5d07c81f5b090336138ab4ddea6d1fd3731d9ce92b716a2f`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-weekday-readback-selector-development.json`, SHA-256 `3a45b8e201242f866a2a673e064fccc4b426617d66298a0352008ae0dcffc9f1`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-weekday-readback-selector-regression.json`, SHA-256 `cbbda5e4e62a678b179808e329eb47ddd2e3d9abb5ce18192942ff0959efde93`. |
| Backend | `3089 passed, 3 skipped`; includes saved weekday and inventory readback regressions. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals, new CI `test:setups`, and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37229966731](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37229966731), all five jobs green. |
| Main CI and Auto Deploy | `PASS`: [main CI 37230213446](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37230213446) and [Auto Deploy 37230380390](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37230380390) on `d32b433a6499d9779e837a5188a4597b6d71abe3`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `d32b433a6499d9779e837a5188a4597b6d71abe3`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
