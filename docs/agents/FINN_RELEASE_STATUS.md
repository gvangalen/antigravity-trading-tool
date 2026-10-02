# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LOCAL_VALIDATION_PASSED`; candidate CI, Auto Deploy and public SHA checks pending. |
| Active goal | Make read-only FINN coaching stable across stop-loss follow-ups, source-bound setup/strategy answers and setups with multiple linked strategies, without replacing correct Luna answers with unrelated fixed or generic verifier copy. |
| Candidate branch | `codex/finn-coach-source-stability` |
| Candidate code SHA | `7fe6e7d0b70534a8b1eb5ec861e6d9fbb6a7fbdd` |
| Candidate PR/head SHA | Pending. |
| Production code SHA | The last authenticated QA run reported backend and frontend SHA `8a6677a6c7ec1df7191dd87bbd09409a465800f6`; the new candidate has not been deployed. |
| Release owner | Build |
| Last updated | 2026-10-02 |

The authenticated QA run on `8a6677a6c7ec1df7191dd87bbd09409a465800f6`
was partially successful and did not accept the coach flow. It found two
generic stop-loss fallbacks, a setup/strategy entry-source mix-up, and an
unstable Apple strategy choice. This batch supersedes the prior candidate.
Build used synthetic local users only; it did not access the protected QA
fixture or sealed holdout.

## Root Causes And Repair

- The FINN setup-link read used a repository method that returned one recent
  strategy even when multiple owner-scoped strategies shared the setup. FINN
  now detects that ambiguity and asks for a strategy choice; an explicitly
  named strategy can be read after its owner and setup link are checked.
- The verifier treated a saved risk/reward ratio as a target price, a
  conditional position-size explanation as a promised trading outcome, and
  a Markdown heading containing a saved English name as an English reply.
  These checks now distinguish typed numeric geometry, risk mechanics and
  short data labels from unsupported claims.
- The turn contract treated the verb `instappen` as a request for a stored
  entry price. It now reserves that requirement for an entry field question.
- Setup entry attribution is checked against the typed linked-strategy read.
  A strategy entry may not be presented as a setup field. General coaching
  remains model-owned when personal plan or market evidence is unavailable.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, API and prefork Celery with
synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`. The
selector development/regression evaluations used configured `gpt-4o-mini`;
this batch does not claim that every safety or selector model is Luna.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses coach regression | `37/37` read-only turns in 13 full conversations; one dispatch per turn; no proposal or write. Includes the exact QA stop-loss, BTC source, BTC/Apple comparison and multiple-Apple-strategy paths. | `.local-finn-parity-artifacts/coach-source-stability-all-release.json`, SHA-256 `765eb48bf2fe08826c789440082cadf437600b57248bf50cb3abff6f923edede`. |
| Full worker-driven safe action-contract matrix | `16/16`; zero broker orders, live-trading calls or live bots. | `.local-finn-parity-artifacts/coach-source-stability-action-matrix-release.json`, SHA-256 `7638e743223b2a1eb5b476f1dcb3a480411cc0f539704ec445179977550847d1`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-source-stability-provider-development.json`, SHA-256 `039506cb358b50a7c0da6556b927e2bb44c5dc9d9f71f23e6bec5d49f30d4b46`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-source-stability-provider-regression.json`, SHA-256 `8a779f540c841c3f3907bf0dd4fc581f1ec3537fa59f00f5037319126f840799`. |
| Backend canonical suite | `2988 passed, 3 skipped` (30 existing deprecation warnings). | `python3 -m pytest -q`. |
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
