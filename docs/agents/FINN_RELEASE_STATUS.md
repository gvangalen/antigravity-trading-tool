# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; Build gates and production identity checks passed. Independent live QA has not run. |
| Goal | Use one owner-scoped, source-checked market, macro and technical benchmark and setupmatch across FINN, My Plan, Analyse, mobile, reports and bot score input. |
| Candidate branch | Merged to `main`. |
| Candidate implementation SHA | `ffdb6b5d97186c96dabbdf6dd91b915d8ade8dc0`; merged in `a34069d9f50ff788fd8bfa2b385189396eeb7e6d`. The security lockfile update is merged in `a51603b565d7ccf7a9922d1b551b67ed83c75a31`. |
| PR | [#80](https://github.com/gvangalen/antigravity-trading-tool/pull/80) and [#81](https://github.com/gvangalen/antigravity-trading-tool/pull/81), both merged. |
| Production SHA | `a51603b565d7ccf7a9922d1b551b67ed83c75a31` observed on both public surfaces after Auto Deploy. A later status-only commit changes the SHA; QA must bind to the current public backend/frontend SHA. |
| Release owner | Build |
| Last updated | 2026-10-06 |

The previous setup-rationale release reached `READY_FOR_INDEPENDENT_QA` on production SHA `e9eac8781260b80fad6267237cbfbf657753c8dd`. No independent acceptance verdict was recorded in this file. The user explicitly requested deployment of the setupmatch change for live testing; this candidate replaces the pending release target.

## Change And Limits

- [Setupmatch contract](../architecture/SETUP_MARKET_MATCH_CONTRACT.md) defines the common score meaning, missing-data states, ranking and bot boundary.
- FINN, My Plan, Analyse, mobile and reports read the same owner-scoped setup conditions and current Analyse weights. Old AI setup scores are not presented as current matches.
- Bot execution uses a proven match only as score input for existing sizing and risk logic. A missing match does not block existing execution. Smart DCA still needs a complete, fresh benchmark for a score-driven amount.
- The old Setup AI Agent was removed. A no-write Celery tombstone remains to drain previously queued messages safely.
- The [live QA test plan](../operations/setup-market-match-live-test-plan.md) lists the required cross-surface and execution checks. Build-local evidence does not establish authenticated production acceptance.
- Main CI initially failed when new npm advisories affected Capacitor and source-map-js. [PR #81](https://github.com/gvangalen/antigravity-trading-tool/pull/81) updated the lockfile and tracked frontend export; the fresh production dependency audit reports zero vulnerabilities.

## Local Build Evidence

All artifacts below are from an isolated local parity stack or repository-local commands. The parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider; the chat model was `gpt-6-luna` with reasoning `none`. The selector used its separately configured provider model. No broker order, live bot, live trading call or production connection occurred in the action matrix.

| Gate | Result | Evidence |
| --- | --- | --- |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/setup-match-action-matrix.json`, SHA-256 `88bc9d1d4b756d45fcea6f779e31bfb3f679b8bc7d8fad50e24a55025c83de74`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-match-selector-development.json`, SHA-256 `8fe3d301ee48374cec3756da950a3c7d6e84e3273e7f65b5015a8bba49cea8fe`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-match-selector-regression.json`, SHA-256 `208425c60dd4fe7d443db0e5f1bca1fd2b1780fc93cfb95bf7e5c7b8fc77cad1`. |
| Owner-scoped score runtime | Isolated DB probe: current weighted benchmark `72.5`, correct BTC ranking and distinct AAPL match; stale source removes benchmark and all numeric matches. | `.local-finn-parity-artifacts/setup-match-runtime-probe.json`, SHA-256 `7c06703f695395023350caf2e5e2fee074d35eb5d09e76e3828b44a2544c2ad7`. |
| Backend | `3127 passed, 3 skipped`; includes twenty-asset, freshness, sync/async parity, old-report and missing-match sizing regressions. | `pytest -q --disable-warnings`; `.local-finn-parity-artifacts/setup-match-pytest.log`, SHA-256 `5405e0620390b4ddc5d14816902b76416adfc35c53152242e53aaaafafdd9866`. |
| Frontend | Typecheck, i18n lint/tests, commands, proposals, setup tests, build and high-severity audit passed; zero high production dependency vulnerabilities. | `.local-finn-parity-artifacts/setup-match-frontend-build.log`, SHA-256 `edb957c9f8168c2ca726a9a7e1e2cfb14e9e47f3cdc1f89c2a935454a2629098`; command outputs in Build turn. |
| Mobile | Typecheck, lint (zero errors; 134 warnings) and Expo web bundle passed. | `.local-finn-parity-artifacts/setup-match-mobile-typecheck.log` and `setup-match-mobile-smoke-web.log`. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | [PR #80 CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37368831098) completed success after hosted-runner rerun; [PR #81 CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37413754628) completed success. |
| Main CI and Auto Deploy | [Final main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37413888897) completed success; [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37414053146) completed success for `a51603b565d7ccf7a9922d1b551b67ed83c75a31`. |
| Public backend health and frontend build-info | On 2026-10-06 both returned HTTP 200 and SHA `a51603b565d7ccf7a9922d1b551b67ed83c75a31`. |
| Independent authenticated live QA | Not started for this candidate; QA owns fixture, execution and verdict. |
