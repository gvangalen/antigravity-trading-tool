# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Make Smart DCA work across catalog assets, retain an open concept for read-only coaching, and reject stale benchmark source data before score-driven execution. |
| Candidate branch | `codex/finn-dca-cross-asset-coach-freshness` |
| Candidate code SHA | `1df343280dfc0880650e22aea6385a3c06094f1d`. |
| PR | [#53](https://github.com/gvangalen/antigravity-trading-tool/pull/53), merged. |
| Production SHA | `2e40d567464808abeedcaa91a96e9fa499560ea4`; public backend and frontend both reported it with HTTP 200 on 2026-10-04. This status-only follow-up will create a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- An explicit positive asset survives a negative mention such as “ETH, not BTC”. This is catalog-wide rather than asset-specific.
- An unconfirmed owner-scoped Smart DCA concept is available to later read-only turns in the same conversation. The model receives a read tool for the draft; the answer verifier does not supply a fixed coaching response.
- Read-only turns cannot propose actions. Explicit asset selection and long separable update commands remain mutation requests.
- Score generation and Smart DCA execution check the age of the underlying macro, market and technical readings. Ingestion now preserves source observation times where the provider supplies them; a missing technical source time is treated as stale.
- `ETH/EUR` is not a separate catalog instrument. The current proposal flow still asks for an asset instead of explaining this capability boundary. No pair was silently mapped to ETH.
- Historical indicator records written before this change may contain receipt timestamps rather than original source timestamps. Independent QA must not treat old rows as proof of source freshness. No authenticated production purchase or saved proposal was tested by Build.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider with synthetic users. It did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Cross-asset draft and coach probe | ETH correction retained ETH; AAPL and MSFT Smart DCA drafts completed. The AAPL draft supported a hypothetical 20/50/80 score follow-up (score 50, planned €60) and a missing-macro follow-up (hold without purchase). ETH/EUR remained a clarification. No proposal was confirmed. | `.local-finn-parity-artifacts/dca-cross-asset-probe.json`, SHA-256 `e8524f7481e293fdd5bdac36cb5ea2119f838c3fc503e254849b32d2cb49fce4`. |
| Worker-driven safe action contracts on final code | `16/16`; zero broker orders, live trading calls or live bots. | `.local-finn-parity-artifacts/dca-cross-asset-final-action-matrix.json`, SHA-256 `b1077fda8616beffa7b37e18c0b44d1413801f9a6931fd51d5854fb6e0b9ad4a`. |
| Real-provider selector development | `18/18`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-cross-asset-selector-development.json`, SHA-256 `0b07ac75a69dcaeb9039ed27cbdf80c9344f7a3e65b03ed323bf3fabdf17b62b`. |
| Real-provider selector regression | `109/109`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-cross-asset-selector-regression.json`, SHA-256 `895c2328ebb3fbf7dbf8909fcca911c38dcda3e42db763751c7e4104cd0d6526`. |
| Backend | `3072 passed, 3 skipped`; score-source and draft tests included. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands and audit:high passed; zero high production dependency vulnerabilities. | Local script output; no frontend source was changed. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37190269634](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37190269634), all five jobs green. |
| Main CI and Auto Deploy | `PASS`: [main CI 37190423504](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37190423504) and [Auto Deploy 37190526075](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37190526075) on `2e40d567464808abeedcaa91a96e9fa499560ea4`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `2e40d567464808abeedcaa91a96e9fa499560ea4`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence and CI do not establish authenticated production acceptance.
