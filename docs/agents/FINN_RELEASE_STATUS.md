# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; Build local gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Let Luna answer read-only coach questions with minimal FINN intervention, while retaining owner-scoped evidence and action boundaries. |
| Candidate branch | `codex/finn-minimal-coach-answer` |
| Candidate code SHA | `aa7ac7b42f5905089051b3f96964adce28992051` |
| PR | [#43](https://github.com/gvangalen/antigravity-trading-tool/pull/43), merged. |
| Production code SHA | `bc48ecb36e78a35faf66e806b582ad31b8afe64e`; both public surfaces returned HTTP 200 with this SHA at 11:01 UTC on 2026-10-03. This status-only follow-up creates a later deploy SHA; verify that identity separately. |
| Release owner | Build |
| Last updated | 2026-10-03 |

The previous authenticated live QA did not accept the coach flow. Build used synthetic local users only; it did not access the protected QA fixture or sealed holdout.

## Change

- Read-only model answers bypass the broad answer verifier. FINN retains owner-scoped tools, action contracts and a narrow check for a saved setup value being falsely attributed to a saved strategy.
- A bounded model repair handles that specific source error. Conversation evidence and references remain available for follow-up turns.
- The provider timeout is 20 seconds and the lifecycle deadline is 30 seconds by default.
- Tailwind CSS is classified as a build dependency so the frontend production audit checks runtime dependencies.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, API and prefork Celery with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`. Selector evaluations used configured `gpt-4o-mini`; this does not claim every selector or safety model is Luna.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses coach regression | `41/41` read-only turns in 14 conversations; one dispatch per turn, no proposals or writes. | `.local-finn-parity-artifacts/coach-minimal-release-41-final.json`, SHA-256 `f7de11f906157b5915406abae7d9ddb1be498bbc9d14197d4856c05855445024`. |
| Worker-driven safe action contracts | `16/16`; no broker orders, live trading calls or live bots. | `.local-finn-parity-artifacts/coach-minimal-release-actions-final.json`, SHA-256 `07a3fbf2a50d013e4b022cf310b9f72fcb0d76431ae987c7d4f360797903cedd`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-minimal-provider-development.json`, SHA-256 `0e7f752943fcb75b834892f9119df045872103d6f15ed644ddc65cd690aba505`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-minimal-provider-regression.json`, SHA-256 `ddd8726585b7d57003a1fdae2292cea16c250bb4416f27ba258b0a7de1904844`. |
| Backend canonical suite | `3008 passed, 3 skipped` (30 warnings). | `python3 -m pytest -q`. |
| Frontend canonical checks | Passed: clean `npm ci`, `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high` (0 vulnerabilities), production `build`. | Local Build run. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [PR run 37118063028](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37118063028), all five jobs green. |
| Main CI | `PASS`: [main run 37118163681](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37118163681), all five jobs green on `bc48ecb36e78a35faf66e806b582ad31b8afe64e`. |
| Auto Deploy | `PASS`: [run 37118257436](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37118257436) deployed `bc48ecb36e78a35faf66e806b582ad31b8afe64e`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 with `bc48ecb36e78a35faf66e806b582ad31b8afe64e` at 11:01 UTC on 2026-10-03. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Local Build evidence supports deployment of this candidate; it does not establish authenticated production coach acceptance.
