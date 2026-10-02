# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_LOCAL_VALIDATED`; CI, Auto Deploy and public identity checks pending. |
| Active goal | Make FINN's read-only coaching and setup-to-strategy follow-ups work as one owner-scoped conversation, including comparisons, ordinal references and an explicit choice among multiple linked strategies, without verifier rewrites of supported Luna answers. |
| Candidate branch | `codex/finn-coach-strategy-continuation` |
| Candidate code SHA | `8747a9e462a434af5961c31cd711e7f1a04c6264` |
| Candidate PR/head SHA | Pending PR creation. |
| Production SHA for this candidate | Not deployed or publicly verified yet. The preceding user-supplied live QA was on `504a20a43c3bd013979508f3000abcc6b1113587`. |
| Release owner | Build |
| Last updated | 2026-10-02 |

The authenticated live QA on `504a20a43c3bd013979508f3000abcc6b1113587`
did not accept the coach flow. The stop-loss and source-attribution repairs
improved, but after FINN asked which Apple strategy was intended, it did not
reliably read the user's explicit choice. Build used synthetic local users
only; it did not access the protected QA fixture or sealed holdout.

## Root Causes And Repair

- A follow-up could discard a verified list ordinal or strategy choice and
  resolve the asset/timeframe again. The continuation now keeps the selected
  owner-scoped setup and strategy IDs, with the setup relationship checked on
  every detail read.
- A comparison read could return inventory fields alone, or pick one linked
  strategy without honoring the user's explicit choice. FINN now reads the
  selected setups and the specifically named linked strategy. An explicitly
  named strategy also triggers its detail read when the model requested the
  inventory tool.
- The answer verifier could treat a prior single-setup focus as the only
  source for a two-setup comparison, or send a plain sourced strategy-field
  answer through another model audit and replace it with a generic fallback.
  Typed factual reads use deterministic source checks. Advice, live-market
  claims, calculations and writes retain the normal controls.
- The turn contract now carries the verified focus and accepts a uniquely
  identified linked strategy in a comparison, while duplicate strategy names
  still require the setup names.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, API and prefork Celery with
synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`. The
selector development/regression evaluations used configured `gpt-4o-mini`;
this batch does not claim that every safety or selector model is Luna.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses coach regression | `41/41` read-only turns in 14 full conversations; one dispatch per turn; no proposal or write. Includes the exact multi-strategy disambiguation and chosen-strategy continuation. | `.local-finn-parity-artifacts/coach-strategy-continuation-all-release.json`, SHA-256 `7ba6c77511b6a4a635e7877b95aa51b5cdb90a10a0d23a69c7dfa312091c564d`. |
| Full worker-driven safe action-contract matrix | `16/16`; zero broker orders, live-trading calls or live bots. | `.local-finn-parity-artifacts/coach-strategy-continuation-action-matrix-release.json`, SHA-256 `130d30d0817374728f6904e0c2e78492ed10ba672a825f005647bcb14c387434`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-strategy-continuation-provider-development-release.json`, SHA-256 `4bca612fab15b53a2dafa94d951dac1aaa0d020b400ecb9b56291a6de8d78e8d`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-strategy-continuation-provider-regression-release.json`, SHA-256 `4374f5eb7c9e99c9b5f6b70aaedce16528a7eb2b80b24e90ca9a75befe2ce36c`. |
| Backend canonical suite | `2995 passed, 3 skipped` (30 deprecation warnings). | `python3 -m pytest -q`. |
| Frontend canonical checks | Passed; no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, production `build`. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Backend health and frontend build-info on candidate SHA | Pending. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Local Build evidence establishes technical readiness for a candidate, not
authenticated production coach acceptance.
