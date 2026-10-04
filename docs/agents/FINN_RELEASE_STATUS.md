# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_PENDING_CI`; local Build gates passed. Production deployment and independent QA are pending. |
| Goal | Preserve the provider observation time for Smart DCA score inputs and explain unsupported quoted pairs without losing a guided request or mapping the pair to its base asset. |
| Candidate branch | `codex/finn-dca-provenance-catalog` |
| Candidate implementation SHA | `cd5e39deab2abd7f28fa221f5033446eebcb75b2`. The status commit will add a later branch SHA. |
| PR | Pending. |
| Production SHA | Previous verified release: `2e40d567464808abeedcaa91a96e9fa499560ea4`; this candidate is not deployed yet. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- Market, macro and technical readings now store `source_observed_at` separately from their receipt timestamp. The Smart DCA score and execution freshness checks read the source time.
- The additive migration leaves historical source times null. A recent receipt timestamp no longer makes a historical reading appear fresh. New verified provider readings can repopulate the field; Smart DCA must wait while a required source time is missing or stale.
- The catalog treats `ETH/EUR` and other unsupported quoted pairs as full instruments. FINN explains that boundary both on a complete request and after an asset clarification, and does not substitute ETH or create a proposal.
- No proposal was confirmed, no purchase was executed, and no authenticated production QA was performed by Build. Local evidence does not establish production acceptance.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider with synthetic users. It did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Source provenance and catalog regressions | Historical rows with missing source time are rejected; provider candle and quote times remain separate from ingestion time; unsupported pair and negation paths covered. | `pytest -q`: `3078 passed, 3 skipped`, 31 warnings. |
| Worker-driven safe action contracts on final code | `16/16`; zero broker orders, live trading calls, live bots or production connections. | `.local-finn-parity-artifacts/dca-provenance-final-action-matrix.json`, SHA-256 `18c3b1e053c8d4b9df1521de60811273930b2dcee1c9baf7a7e67a76fd4cf6ea`. |
| Real-provider selector development | `18/18`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-provenance-selector-development.json`, SHA-256 `75a7e0f83c9528d066f7da93391186caf18f246bf9b8d0bb73955077e91a2088`. |
| Real-provider selector regression | `109/109`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-provenance-selector-regression.json`, SHA-256 `a5d5350dd1ca857f55329e4636991902ed1ff0d003e77bd428e3d25318bcc0fc`. |
| Full local runtime pair probes | Complete `ETH/EUR` request and two-turn clarification both completed with no proposal and an explicit catalog answer. | `.local-finn-parity-artifacts/dca-provenance-pair-final.json`, SHA-256 `5bf802f8e2f9a7ecb7674b84ca19a90ecc5c3fbbdf1036ed33c8717addad1000`; follow-up artifact SHA-256 `79b71e89dd46f011b500c32f1f108d760f860f70e911e71454885ed19dd08e06`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands and audit:high passed; zero high production dependency vulnerabilities. | Local script output; no frontend source was changed. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI and Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending for this candidate. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence and CI do not establish authenticated production acceptance.
