# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity checks passed; independent authenticated QA remains pending. |
| Goal | Keep owner-scoped MA 200 configuration pending without a fabricated reading when its technical source rate-limits; replace the 429→500 generic failure with an explicit pending-source response and UI message. |
| Candidate branch | Merged to `main` in `ff038fbed0987bb69acb97e456352589b8a47a89`. |
| Candidate implementation SHA | `487eba47c0e7462fb1f94b6aa110e547e2bb790d` |
| PR | [#91](https://github.com/gvangalen/antigravity-trading-tool/pull/91), merged. |
| Previous live SHA | `78d3d873fae8328b29ae6c10c267e85e33a64edc`, targeted live QA passed curve/weight persistence, duplicate Price validation and FINN emphasis, but MA 200 hit provider HTTP 429 and the app returned HTTP 500. |
| Production SHA | `ff038fbed0987bb69acb97e456352589b8a47a89` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

This batch classifies Twelve Data and Binance technical HTTP 429 responses as temporary source limits. A user-triggered indicator addition persists its owner-scoped configuration with `value: null` and `score: null`; Analyse already projects configured technical indicators without readings as pending rows. A scheduled refresh still counts a rate-limited read as failed. The API commits the pending configuration and the frontend states that no score exists yet. It neither retries a rate-limited provider immediately nor invents a reading.

Measured local evidence: root pytest **3155 passed, 3 skipped**, `.local-finn-parity-artifacts/technical-rate-limit-pytest.log` SHA-256 `81b9bc1aaf4a0b203f47618eef05f0f8bbef51a00376f1293627cdbe5e8268ca`; frontend build, typecheck, i18n, commands, proposals and production high-severity audit passed, `.local-finn-parity-artifacts/technical-rate-limit-frontend-build.log` SHA-256 `26fc0866f3ef5a45fea1925ba26ade9030a08acda251cbc2cd6c9d7169416a2a`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, zero prohibited executions, `.local-finn-parity-artifacts/technical-rate-limit-full-action-matrix.json` SHA-256 `236889f1337cb0eebeaf673a918ae71781b32b61e81a6ebb40c080354b6ace4f`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/technical-rate-limit-selector-development.json` SHA-256 `5a8110a9a78922ad7a917cc2d85e6ba5a89cc22ec08257b748de61ca2295fd45`; regression passed **109/109**, `.local-finn-parity-artifacts/technical-rate-limit-selector-regression.json` SHA-256 `940defc1bf82fa8367dc95ad590f036108513ef7fcb97eee0efb72c02969fb9e`. Both runs had zero provider, schema, parse, validation or timeout failures. The 429 branches were injected in local backend tests; this is not an authenticated live test of an actual rate-limited provider. Complete fresh-source positive setupmatch and score-driven Paper execution remain unproved.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37518522551) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37518779838) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37519034762) completed success for `ff038fbed0987bb69acb97e456352589b8a47a89`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. Independent QA should verify the real provider-limit case, the persisted pending technical row after refresh, the absence of a false score/setupmatch, and the later transition to a dated value when the source recovers. The positive match and paper-bot decision need complete fresh sources.

## Previous Release (indicator score curve persistence)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated QA passed curve/weight persistence, duplicate Price validation, and FINN emphasis on `78d3d873fae8328b29ae6c10c267e85e33a64edc`; MA 200 exposed a provider 429→API 500 failure. Positive-match and Paper execution acceptance remain open. |
| Goal | Preserve custom indicator curves and weights across configuration writes, show actionable validation errors, prevent duplicate-selection side effects, and render FINN's single-star setup emphasis. |
| Candidate branch | Merged to `main` in `1e35609aacb1274f16e4eb7eb84de810356299b8`. |
| Candidate implementation SHA | `07da8518928ddcf33d3125d942267fe010aa0af6` |
| PR | [#89](https://github.com/gvangalen/antigravity-trading-tool/pull/89), merged. |
| Previous live SHA | `ee1e49ad8fc0c20d3dab685a73937fd718803140`, independently checked for the missing-data and duplicate-indicator paths. |
| Production SHA | `1e35609aacb1274f16e4eb7eb84de810356299b8` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The independent live check of the previous release found that Analyse and FINN correctly keep incomplete BTC scores and setup matches unavailable, an unscored Volume indicator persists, and a duplicate Price indicator receives a clear error. It did not inspect the raw `null` payload, retest the separate insufficient-history validation error, or prove a positive match with complete fresh sources. These remain evidence limits, not green release claims.

This batch fixes a further configuration defect found during follow-up: saving custom five-band rules and then saving settings could overwrite the rules. The frontend now submits the custom curve and weight together, and the backend preserves existing custom rules on settings updates. Adding a duplicate indicator now fails before configuration writes. The dialog surfaces 400/422 validation details and accurately reports partial creation when a later settings write fails. FINN's text renderer handles single-star emphasis around setup names.

Measured local evidence: root pytest **3149 passed, 3 skipped**, `.local-finn-parity-artifacts/indicator-score-followup-pytest.log` SHA-256 `84b5994f29c635ba83cfef6fe18dafa54aa3253776cf0af257dd3d5d9476be37`; frontend production build and typecheck passed, `.local-finn-parity-artifacts/indicator-score-followup-frontend-build.log` SHA-256 `fe6def5111edb7ed220fb20089ed08c18a44d6680ccc4a9f0cc19e55a4f3e68a`; frontend i18n, commands, proposals, focused config/chat tests and high-severity dependency audit passed, with zero reported vulnerabilities. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/indicator-score-followup-full-action-matrix.json` SHA-256 `6a5c1366911bb7e5424cc6fcd90d92fabf50ffb1ae0fe4f4e137382882431e83`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/indicator-score-followup-selector-development.json` SHA-256 `41c2e28197c422c945c6ab7036a33e84bc2cd861c4e45ee20b2780a02e74b9c3`; regression passed **109/109**, `.local-finn-parity-artifacts/indicator-score-followup-selector-regression.json` SHA-256 `671b4c8e648f12f75a5a91ff0f09012913cd5b7151612ad25aeb04085d398da4`. Both runs had zero provider, schema, parse, validation or timeout failures. A synthetic, owner-scoped positive setup-match test covers fresh and stale source evidence locally; it does not establish a live positive match or paper-bot decision with five genuinely dated observations.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513073466) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513368649) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513638120) completed success for `1e35609aacb1274f16e4eb7eb84de810356299b8`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. Independent QA should verify the raw missing-score payload, custom five-band rule/weight persistence, a visible insufficient-history error, FINN setup-name formatting, and a positive match/paper decision only with complete genuinely dated fresh sources.

## Previous Release (indicator score presentation)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Independent live QA passed the targeted missing-data and duplicate-indicator checks on `ee1e49ad8fc0c20d3dab685a73937fd718803140`; positive-match and separate validation-error acceptance remain open. |
| Goal | Repair stale and incomplete indicator-score presentation, preserve missing values in FINN evidence, and allow unscored market indicator configuration while history accumulates. |
| Candidate branch | Merged to `main` in `e7addf5459b08d39509726e21e6334624ddcefb8`. |
| Candidate implementation SHA | `d3c764cdcfa9bc2d804e5b0967c2398b13df714e` |
| PR | [#87](https://github.com/gvangalen/antigravity-trading-tool/pull/87), merged. |
| Previous live SHA | `3b2664f89b37b13fdde8d127bf1350a2c070138b`, independently tested and not accepted. |
| Production SHA | `e7addf5459b08d39509726e21e6334624ddcefb8` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The new Build batch keeps a raw indicator reading separate from a validated score. Analyse day cards and row explanations use the canonical daily score and its indicator evidence. FINN preserves missing macro and technical scores as `null` and exposes the original source timestamp. A market indicator with too little dated history can be configured but remains unscored. The config dialog now explains duplicate-indicator failures inline. These fixes do not create the missing five-observation production fixture or prove a positive match or paper execution.

Measured local evidence: root pytest **3145 passed, 3 skipped**, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-pytest.log` SHA-256 `ecd9df3e79c791764637f1be6f32a7c677204840503a751006cb51ce56f88a03`; frontend production build and typecheck passed, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-frontend-build.log` SHA-256 `0853c8d97c722f652189763c03c7c6fdade2bca2d238f1b53c06cdd7904799d3`; frontend i18n, commands, proposals and high-severity production audit passed with zero vulnerabilities. The new canonical-score presentation tests passed **2/2**. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, zero prohibited executions, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-full-action-matrix.json` SHA-256 `a8168eb0a1a93d52f1cb7e5a457a22e544d3d40358f8e93cdcd073d222aff19d`. Real-provider selector development passed **18/18**, SHA-256 `c61e11db46079b72471e615c4bac81dbcaac36bc4bcd4ec1d81873c8c003f747`; regression passed **109/109**, SHA-256 `bf414d7cdc37fceb4be4870abdbe09495221dc8fc5ae9337a7475d2d5783393a`, with zero provider, schema, parse, validation or timeout failures. Their artifacts share the `indicator-score-v2-qa-fix-selector-` prefix in `.local-finn-parity-artifacts/`.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37506880820) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37507227211) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37507564081) completed success for `e7addf5459b08d39509726e21e6334624ddcefb8`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. The next QA pass must check AAPL stale DXY and one-observation Price presentation, FINN's S&P 500 missing-score semantics, duplicate and insufficient-history indicator configuration, and a controlled positive setupmatch/paper decision only when five genuinely dated measurements per required source are available.

## Previous Release (indicator score flow v2)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; this candidate is not independently accepted. |
| Goal | Unify indicator scoring and dated benchmark evidence across FINN, Analyse, Mijn Plan, reports, mobile and bot score input. |
| Candidate branch | Merged to `main` in `56e8a255ad34b74391ec0ae28724e4eb55ddaf95`. |
| Candidate implementation SHA | `a492d7e1f660dcdf60437fe7a7756bb836757722` |
| PR | [#85](https://github.com/gvangalen/antigravity-trading-tool/pull/85), merged. |
| Previous live SHA | `cb0c24827a853c616e0145d652f5353f2e9f8d24`. |
| Production SHA | `56e8a255ad34b74391ec0ae28724e4eb55ddaf95` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The score-flow code passed local root pytest (3142 passed, 3 skipped), frontend build, mobile typecheck/lint/web smoke and migration plan validation. The frontend export was rebuilt, and the production dependency audit passed with zero vulnerabilities after updating the `sharp` override. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37498674203) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37499125577) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37499391196) completed success for `56e8a255ad34b74391ec0ae28724e4eb55ddaf95`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06.

The isolated local PostgreSQL/Redis/FastAPI/prefork Celery stack used the real Responses provider and synthetic fixture users. The worker-driven safe-action matrix passed **16/16** with zero prohibited executions: `.local-finn-parity-artifacts/indicator-score-flow-v2-full-action-matrix.json`, SHA-256 `10c048fd645a6ac49ed701f6c88b8c0a950a87bad1e0d604e3e6d0de15071d96`. Real-provider selector development passed **18/18**: `.local-finn-parity-artifacts/indicator-score-flow-v2-selector-development.json`, SHA-256 `eb416a8e6a45cb67854e4c7a425cdc497376162c65d91ac48179f2edb4ddc170`. Real-provider selector regression passed **109/109**: `.local-finn-parity-artifacts/indicator-score-flow-v2-selector-regression.json`, SHA-256 `63f984a2a1c9e045db9fa59da9cde06018ca85f4c9f476500a98ac44dc939728`. Both selector runs had zero provider, schema, parse, validation and timeout failures. The isolated migration completed successfully. Independent authenticated live QA later tested production SHA `3b2664f89b37b13fdde8d127bf1350a2c070138b` and did not accept the score flow because of stale partial scores, missing-to-zero FINN evidence and configuration errors.

## Previous Release (setup-score repair)

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
