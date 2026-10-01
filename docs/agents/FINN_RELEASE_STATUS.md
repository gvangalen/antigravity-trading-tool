# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; Build release gates passed. |
| Active goal | Improve the evidence follow-up after FINN identifies a numbered saved setup: on “Wat weet je daarvan zeker?” name the reread source, confirmed fields, and unverified limits. The user's targeted live retest of the prior defects passed on `9666f39db37607f1157ed71e06cc9b82080f434a`; this answer-quality gap remained. |
| Candidate branch | `codex/finn-listed-setup-evidence` ([PR #27](https://github.com/gvangalen/antigravity-trading-tool/pull/27), merged). |
| Candidate code SHA | `c00fc760`; merge SHA `220ae2d4dda16c5eae657bea870c16d7f67cd17e`. |
| Production code SHA | `220ae2d4dda16c5eae657bea870c16d7f67cd17e`, verified on public backend health and frontend build-info at 08:21 UTC on 2026-10-01. This status-only follow-up creates another deploy SHA; verify that runtime identity separately. |
| Release owner | Build |
| Last updated | `2026-10-01` |

The preceding candidate and its targeted live QA report remain historical
context. This is a new local repair batch. Build did not use the protected
production QA fixture or sealed holdout and did not run authenticated
production QA.

## Root Cause and Repair

The numbered setup answer was grounded by a verified owner-scoped inventory
read, but an anaphoric evidence question did not preserve that selected-item
reference. The following model-led answer could repeat the name without
explaining its evidence. The preprocessor now recognises a question about what
is certain as an evidence follow-up. When the immediately preceding verified
turn selected a numbered setup, the Responses front door validates its saved
ID and reads that owner-scoped setup again. The answer verifier names only
fields returned by the fresh read and explains that the setup inventory did
not check an entry confirmation or linked strategy. Missing or mismatched
prior evidence cannot select an ID.

## Local Build Evidence

The parity stack used isolated PostgreSQL, Redis, API, and Celery with synthetic
users. FINN chat used `gpt-6-luna` with reasoning `none`; selection and semantic
verification used `gpt-4o-mini`. Artifacts are ignored files under
`.local-finn-parity-artifacts/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact list → second setup → evidence follow-up via API/Celery | `3/3` completed, no proposals. The follow-up names `BTC Full Base`, confirms BTC/4H/trade from the reread setup, and states what was not checked. | `evidence-followup-repro.json`, SHA-256 `5f0a7d3ebe6a84a1c40279489da584afa502e4188a5a25c02a5dc3d3a5d00dde`. |
| Full safe action-contract matrix on final local build | `16/16`; zero broker orders, live bots, live-trading calls, or production connections. | `listed-evidence-action-matrix.json`, SHA-256 `a6fec3619a199e8ac22e4624582cfcfdc74e9ac5c721139feaf5a9bc60a11052`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, or timeout failures. | `listed-evidence-provider-development.json`, SHA-256 `59dc34ada8488e503140b86892286817141b5ad56f776b0b71888763750a6764`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation, or timeout failures. | `listed-evidence-provider-regression.json`, SHA-256 `c284b93d3e0583661d5d70edfa8c53e79509e4039c8f9004afc0bc749681566b`. |
| Backend canonical suite | `2914 passed, 3 skipped`. | `pytest -q --disable-warnings` on final code. |
| Frontend canonical checks | `PASS`; no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, and production `build`. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36834333984`, all five jobs green. |
| Main CI | `PASS`: main run `36835506591`, all five jobs green. |
| Auto Deploy | `PASS`: run `36835662943` deployed merge SHA `220ae2d4dda16c5eae657bea870c16d7f67cd17e`. |
| Backend health and frontend build-info | `PASS`: both HTTP 200 and both reported the merge SHA at 08:21 UTC on 2026-10-01. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Build's local checks establish technical readiness only. Authenticated
production acceptance remains independent QA's responsibility.
