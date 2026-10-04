# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_CI_PENDING`; local Build gates passed, candidate is not deployed. |
| Goal | An explicit correction without a replacement ticker must withdraw the old proposal, ask for the ticker, and continue the original DCA draft without reviving the old asset. |
| Candidate branch | `codex/finn-unknown-asset-correction` |
| Candidate implementation SHA | `1f421544b65c82e35038051c7969140286b91379`; followed by this release-status commit. |
| PR | Pending. |
| Production SHA | `15ea7610bf3c481de48e816ca8eb1b1eca7e2a3e`; public backend and frontend both reported it with HTTP 200 on 2026-10-04 before this repair. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- The user-provided live browser QA on `15ea7610bf3c481de48e816ca8eb1b1eca7e2a3e` found two confirmable ETH cards after “ik bedoel een aandeel in plaats van ETH”; no confirmation was clicked. That release was not accepted for this correction path.
- A direct owner- and conversation-scoped asset correction cancels the old proposal before selecting a replacement. A category correction such as “een aandeel in plaats van ETH” now does the same even without a ticker.
- A missing ticker stays a collecting slot. The previous asset cannot be inferred from the user's rejection clause or reused from the previous card. After a supported ticker, non-asset DCA fields remain available; if the old name contains the rejected ticker, FINN asks for a new name.
- A provider-regression run exposed one unrelated typed-read omission: an explicit RSI mention could be absent from `read_indicator_configuration` entities. The selector now preserves the owner's explicit indicator concept; this does not modify the coach answer.
- Hypothetical questions leave proposals untouched. The existing server confirmation boundary rejects cancelled proposals; no trade or plan was executed by Build.
- Build validation uses synthetic local users. Independent authenticated production QA remains pending.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector evaluation gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| ETH → unspecified stock → AAPL → new name | Old ETH proposal `cancelled`; old publish HTTP 409; ticker and name requested; only a new AAPL draft created. | `.local-finn-parity-artifacts/proposal-unspecified-asset-result-release.json`, SHA-256 `8e88f34162dc11bb54e52f040991249d722deeaf82c6d07ae2fd5de7279c749f`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/unspecified-asset-action-matrix-release.json`, SHA-256 `e7e8348fbd1d03a56fbe6a109c4d3e2c6abf9efd5823ad7085f00cac6ce4d150`. |
| Real-provider selector development | `18/18` on final code; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/unspecified-asset-selector-development-release.json`, SHA-256 `6e2e95bd15e383bdf601643f03f016fda9c9c6cf263b041539ab4679faee75e8`. |
| Real-provider selector regression | `109/109` on final code; zero provider, schema, parse, validation or timeout failures. The prior run's explicit RSI omission is covered. | `.local-finn-parity-artifacts/unspecified-asset-selector-regression-release.json`, SHA-256 `04c6fffd2ffeb9ab57b41f77fe077d83f1776f06e76bfe8f2e37e36c50d8e417`. |
| Backend | `3083 passed, 3 skipped`; includes unspecified correction, hypothetical negative, multi-turn slot and explicit RSI read tests. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI and Auto Deploy | Pending. |
| Public backend health and frontend build-info | Previous production SHA only; candidate pending. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
