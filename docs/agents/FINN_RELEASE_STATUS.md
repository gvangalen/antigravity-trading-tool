# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; this candidate is not independently accepted. |
| Goal | Repair Analyse ↔ FINN score evidence, setup-boundary reads with multiple strategies, exact Smart-DCA threshold readback, and the paper-bot `NaN` display. |
| Candidate branch | Merged to `main` in `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Candidate implementation SHA | `cece6f8ce964a3df7c29c1992ee85cf23af7b1c9` |
| PR | [#83](https://github.com/gvangalen/antigravity-trading-tool/pull/83), merged. |
| Previous live SHA | `82f8b6bec76b80234e4a8b1222aa96fb9cd5cc3b`, reported by independent live QA as not accepted. |
| Production SHA | `1f50e2f3adc682de0bf2f468be7aaddbc89e4561` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Release owner | Build |
| Last updated | 2026-10-06 |

## Change And Limits

- FINN reads the same owner-scoped saved daily market score as Analyse. It receives source status separately and does not treat a reported score as a verified complete benchmark.
- Saved setup score boundaries remain readable without choosing among linked strategies. The setup-match tool carries those conditions even when current scores are incomplete.
- Smart-DCA score bands and hypothetical amounts are derived from the execution curve engine. Exact score 70 selects the high band in a 40/70 step curve.
- The paper-bot card displays a missing stop-loss instead of `€ NaN`.
- A dated score report can be read even when it precedes today; its report date does not establish current source freshness.
- The [live test plan](../operations/setup-market-match-live-test-plan.md) includes the QA regressions. The one generic failure turn has no runtrace, so its exact cause is not established. A positive match, paper-bot decision with fresh sources, and authenticated cross-surface behavior remain for independent QA.

## Measured Local Build Evidence

All runtime artifacts below used an isolated local PostgreSQL, Redis, FastAPI and prefork Celery stack with the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`. The selector used its separately configured provider model. The local matrix made no broker orders, live bot activations, live trading calls or production connections.

| Gate | Result | Evidence |
| --- | --- | --- |
| Worker-driven safe action contracts | `16/16`; zero prohibited executions. | `.local-finn-parity-artifacts/setup-match-qa-fix-full-action-matrix.json`, SHA-256 `5fc3d48fba1815bf4e88cdb461bae9144820a7c7ae6e42673c952d6e8cdc92fd`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-match-qa-fix-selector-development.json`, SHA-256 `af7d0cf41d9597ad74ef946145575274392c2a741ac269c03537010e5db7c886`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. Selector implementation was unchanged after this run. | `.local-finn-parity-artifacts/setup-match-qa-fix-selector-regression.json`, SHA-256 `ae6dcfa79f07048bc30182d0430f829c00bf9a8aadbf71794b0fce83ac2a726d`. |
| Local Responses/API/Celery conversation | Named BTC setup bounds with two strategies, follow-up against incomplete scores, saved market score 100 with stale source, and exact Smart-DCA score 70 → €90 all completed read-only. | `.local-finn-parity-artifacts/setup-match-qa-fix-live-probe.json`, SHA-256 `cb5173f4961678f75fa8fb21d1f471d28009aa8c1d5db9bd14c4f8942099ed88`. |
| Dated saved-score conversation | Both turns completed read-only; prior score report date and three values read, no current trade signal inferred. | `.local-finn-parity-artifacts/setup-match-qa-fix-score-date.json`, SHA-256 `d3512dfd695c40765cc328f55c561019fe61ffb5f5346fcdb87dbea678a44ab7`. |
| Backend | `3133 passed, 3 skipped`; includes typed tool, source-status, setup-boundary, Smart-DCA threshold and conversation regressions. | `pytest -q --disable-warnings`; `.local-finn-parity-artifacts/setup-match-qa-fix-pytest.log`, SHA-256 `3aa5133d49c48836ff3ade3da2bae0cf49717aeed19f61f92b66929df5873bc1`. |
| Frontend | Build, typecheck, i18n lint/tests, commands, proposals, setup tests and high-severity production dependency audit passed; zero vulnerabilities. | `.local-finn-parity-artifacts/setup-match-qa-fix-frontend-build.log`, SHA-256 `7adc82013f7addf1e524a5f4cba3ae91b7da2aa70c0a0ca4bf72a4e062744d6f`. |

An additional 37-case public parity runner was tried and did not pass. Its old DCA setup prompt lacks the now-required amount, so clarification is correct, while its read probes require legacy operation IDs absent from the current model-led chat route. This runner is not the required 16-action contract gate; its mismatch is recorded rather than counted as green.

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | [PR #83 CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37420681594) completed success. |
| Main CI and Auto Deploy | [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37420888542) and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37421015126) completed success for `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Public backend health and frontend build-info | On 2026-10-06 both returned HTTP 200 and SHA `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Independent authenticated live QA | Pending for this candidate; only QA owns the fixture and verdict. |
