# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LOCAL_VALIDATION_COMPLETE`; candidate CI and deployment pending. |
| Goal | Address the source date missing beside Analyse scores, the zero-quantity bots shown as positions, and the intermittent score-date coach failure without restoring broad answer overrides. |
| Candidate branch | `codex/finn-score-date-and-positions` |
| Candidate code SHA | `ca474f270a75f9ba819caf70e5f6308c9554d6b5`; source and frontend export. |
| PR | Pending. |
| Production SHA | Prior live QA tested `49e210b5fe5299e59ed76fb1dab8ac6420de56b7`; this candidate has not been deployed. |
| Release owner | Build |
| Last updated | 2026-10-03 |

The user supplied independent authenticated live findings for the prior SHA. Build used synthetic local users only and did not access the protected QA fixture or sealed holdout. The exact failing score-date prompt and live trace were not supplied; the provider failure mechanism in that particular turn remains unproven.

## Change

- The Analyse score cards show the oldest source timestamp of the indicator rows used for each displayed score, or say when source dates are incomplete. They distinguish saved context scores from current trading signals. The combined score label comes from those same visible rows.
- The lower bot portfolio section counts only bots with nonzero net quantity as open positions. When none exist, it says so instead of showing zero-valued positions; bot budget limits remain separate.
- The score tool reads the latest saved owner-scoped daily report, including an older report, and preserves its report date. Daily-score freshness uses a one-day window.
- A transient Responses provider failure after read evidence gets at most one retry within the request budget. The response remains model-authored. The default lifecycle deadline is 40 seconds. A typed plan-evaluation tool choice now stays consistent when the model has identified a plan concept.
- The local coach-regression check no longer treats a statement that a favourable ratio **does not** prove profitability as unsupported positive advice.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, API and prefork Celery with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`; selector evaluations used the configured `gpt-4o-mini` and do not prove that every model call used Luna.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses score-date regression | Two read-only turns passed; latest saved report date and scores in typed evidence and answer; no proposal or false live signal. | `.local-finn-parity-artifacts/score-date-candidate-final.json`, SHA-256 `d54a2b317131f3e74f8fdeaa8f11ffcb2ecd164a73ca62a054f67d6554d23080`. |
| API/Celery/Responses portfolio control | Two read-only turns passed; bot budget, retrieval date and cash boundary remained correct. | `.local-finn-parity-artifacts/score-date-portfolio-final.json`, SHA-256 `3d1ecf39b18924d1c35329278b002941e94438ab7e502b3155f8bf3d1ebf70a7`. |
| API/Celery/Responses coach control | Four read-only cases passed, including stop-loss and risk/reward; no proposals or generic fallback. | `.local-finn-parity-artifacts/score-date-coach-corrected-final.json`, SHA-256 `fbe8530189faf8e68200916c0dfd05adda41d730d0a21bb21d7dd8d15e268314`. |
| Worker-driven safe action contracts | `16/16`; no broker orders, live trading calls or live bots. | `.local-finn-parity-artifacts/score-date-actions-canonical-final.json`, SHA-256 `8fdaf3340a71cc601197a8e398bd916c091484666bcf4621fe707e83e5b8ffa6`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/score-date-selector-development-final.json`, SHA-256 `77313829bb107d0b4794c5f11de58bd90dbc4f67065a39845d92da6a37b96003`. |
| Real-provider selector regression | `109/109` after the final tool-choice consistency change; zero provider, schema, parse, validation or timeout failures. The first pre-change run had one plan/setup misclassification (`108/109`); its unmodified repeat was `109/109`. | `.local-finn-parity-artifacts/score-date-selector-regression-final.json`, SHA-256 `805f72d87f0e174a5ae3b3659a9ed21e2d5cf931286ffae028e23a29a5a507d9`. |
| Backend canonical suite | `3016 passed, 3 skipped` (30 warnings). | `python3 -m pytest -q`. |
| Frontend canonical checks | Passed: `typecheck`, `lint:i18n`, `test:i18n` (8), `test:commands` (5), `audit:high` (0 vulnerabilities), production `build`. | Local Build run. |

An additional legacy 37-case parity matrix completed with all 16 action contracts and 9 lineage cases passing, but its overall result was red: read-only cases expected selector operation IDs that the current model-led chat path did not return. Artifact `.local-finn-parity-artifacts/score-date-actions-final.json`, SHA-256 `4226ad13f8a72b5e7d958762557be95d1c67d397d5712cf4394682bb8c84b968`. This result is **not** counted as a green release gate and needs a separate contract review; the required canonical action matrix above passed.

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Local Build evidence does not establish authenticated production coach acceptance.
