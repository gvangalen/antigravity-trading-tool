# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LOCAL_VALIDATED`; candidate CI and deployment pending. |
| Goal | Align FINN and the web UI on bot budget, portfolio valuation, retrieval dates and score source dates without restoring broad answer overrides. |
| Candidate branch | `codex/finn-portfolio-evidence-alignment` |
| Candidate code SHA | `34ab48a6` (the source and export commit; this status commit follows it). |
| PR | Pending. |
| Production SHA | Not yet verified for this candidate. |
| Release owner | Build |
| Last updated | 2026-10-03 |

The prior authenticated browser test on `271ffb22fa54b8ae29d2d91255415e7cef859f78` identified the bot budget, portfolio and date discrepancies. Build used synthetic local users only and did not access the protected QA fixture or sealed holdout.

## Change

- FINN's owner-scoped portfolio tool now exposes a retrieval time separately from the timestamp of market prices. Budget is a limit and cannot fill cash or equity fields.
- A read-only `/api/portfolio/summary` route uses the same portfolio adapter as FINN. The portfolio card requires that adapter's valuation availability before showing history; a historical snapshot is dated and is not presented as spendable cash.
- Bot budget labels no longer call a calculated remainder “available”. The portfolio history queries return the most recent window in chronological chart order.
- Daily scores expose their saved report date; score cards show source dates and avoid treating missing values as zero or a saved score as a current trade signal.
- Guidance to Luna distinguishes combined plan/market/portfolio questions and keeps internal field names out of user-facing answers. The broad answer verifier remains bypassed for read-only coaching.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, API and prefork Celery with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`. Selector evaluations used configured `gpt-4o-mini` and do not claim that every model call used Luna.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses portfolio regression | Two read-only turns passed; one dispatch and attempt each, no proposals. The shared summary route passed six budget, cash, valuation, date and ownership checks. | `.local-finn-parity-artifacts/portfolio-evidence-candidate-final.json`, SHA-256 `db0d695d21d0d2d739136a0fc085f6d9012d9951d28b6a598a96241813938596`. |
| Worker-driven safe action contracts | `16/16`; no broker orders, live trading calls or live bots. | `.local-finn-parity-artifacts/portfolio-evidence-actions-final.json`, SHA-256 `bb462d20fc2d7ae8a99a9f2b56559d9e0cbd0a9a98d3d6c0401c6f7f517be373`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/portfolio-evidence-selector-development-final.json`, SHA-256 `a2f2395ac7e38aeeba3af1033f28044d83a8b08f8c0c7971090a3d75dfb043f4`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/portfolio-evidence-selector-regression-final.json`, SHA-256 `35fc3b86e14158ca6d3a97a5e65fbddad94da88b097f32f3766080936cd029fe`. |
| Backend canonical suite | `3012 passed, 3 skipped` (30 warnings). | `python3 -m pytest -q`. |
| Frontend canonical checks | Passed: `typecheck`, `lint:i18n`, `test:i18n` (8), `test:commands` (5), `audit:high` (0 vulnerabilities), production `build`. | Local Build run. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending for this candidate. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Local Build evidence supports creating one candidate. It does not establish authenticated production coach acceptance.
