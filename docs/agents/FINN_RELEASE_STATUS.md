# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_VALIDATED`; production deployment pending. |
| Goal | Smart DCA uses the total current Market, Macro and Technical benchmark for a percentage ladder around a base amount. Fixed DCA and paper execution remain distinct. |
| Candidate branch | `codex/finn-smart-dca-contract` |
| Candidate code SHA | `2ed4fdc837cb4d650b9faa9891879a53f97047f2` |
| PR | [#49](https://github.com/gvangalen/antigravity-trading-tool/pull/49), draft at this stage. |
| Production SHA | Pending Auto Deploy and public identity checks. |
| Release owner | Build |
| Last updated | 2026-10-03 |

The user explicitly selected the existing combined benchmark as the only Smart DCA score source, using the current Analyse weights. There is no legacy market-only Smart DCA mode in this candidate. Build used synthetic local users and did not access the protected QA fixture or sealed holdout.

## Change

- FINN creates Smart DCA as a setup cadence plus a linked strategy with a base amount and score-to-percentage ladder. The proposal card shows the source, thresholds, and resulting amounts before confirmation.
- The paper decision path uses the total Market/Macro/Technical benchmark and current weights. Missing score components prevent a score-based purchase. Fixed DCA remains separate from the Smart DCA ladder.
- Setup, strategy and bot evidence expose the stored plan through typed contracts for later FINN readback.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, API and Celery with synthetic users; the FINN chat path used the real Responses provider. No production account or live order was used.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses positive and negative Smart DCA path | Positive proposal and paper sizing exercised; market-only request produced no confirmable Smart DCA proposal. | Local parity artifacts. |
| Paper sizing | Benchmark scores 32/60/80 gave €10/€100/€150; missing Macro held at €0; no duplicate buy. | Local paper probe artifact, SHA-256 `0b0eb18f9c89ee14ecb900366e5827e7eb6aa8da5b4327dcfc6125279e084d47`. |
| Worker-driven safe action contracts | `16/16`; no broker orders, live trading calls or live bots. | `.local-finn-parity-artifacts/benchmark-only-action-matrix.json`, SHA-256 `1831d34c84649b062730bf0ff8a7954e6f9ac142a0546454d271bd68b4963860`. |
| Real-provider selector development | `18/18`; no provider, schema, parse, validation or timeout failures. | Local selector development artifact. |
| Real-provider selector regression | `109/109`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/benchmark-only-selector-regression.json`, SHA-256 `9148cbe5e4e1ff21b465fddc4488f6731ac7cc606e83864bcba179f05004b5c2`. |
| Backend canonical suite | `3055 passed, 3 skipped`. | `python3 -m pytest -q`. |
| Frontend canonical checks | `build`, `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high` passed. | Local Build run. |

The daily score row date can be current even when an underlying indicator is older; component-level source freshness is not independently enforced in this candidate. QA should assess the visible score date and score-driven paper decision accordingly.

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [PR run 37146476417](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37146476417), all five jobs green on candidate code SHA. Status-only candidate commit requires its own CI. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence and CI do not establish authenticated production acceptance.
