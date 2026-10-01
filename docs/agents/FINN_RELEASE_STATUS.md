# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILD_CANDIDATE`; local required gates passed, CI and deployment pending. |
| Active goal | Repair FINN's recurring multi-turn coach failures as one flow: keep the current question and selected owner-scoped setup evidence through comparisons, risk tradeoffs, corrections and linked-strategy follow-ups, without fixed coach copy replacing the answer. |
| Candidate branch | `codex/finn-turn-contract`. |
| Candidate code SHA | `80324808ec474b163bfc727f29291b3ce63dcd47`. |
| Candidate PR/head SHA | Pending. |
| Production code SHA | Pending for this candidate. Previous verified release: `2c0423a93cab418071042a9150608cd5419abffd` at 13:26 UTC on 2026-10-01. |
| Release owner | Build |
| Last updated | `2026-10-01` |

The previous release was marked `READY_FOR_INDEPENDENT_QA`, but the user's
subsequent live report on SHA `3ad45d1486936abd2104139172180ada9bf01e85`
showed further related failures. No independent QA run for this new candidate
has started.

## Root Causes and Repair

- A broad objection rule matched “te streng” and replaced a stop-distance and
  position-size question with fixed waiting-time copy. The fixed override was
  removed; the current question's risk tradeoff is now checked for coverage.
- Comparison reads reduced a request containing `4H` and `1D` to the first
  timeframe, then listed matching records. Explicitly named setups are now
  selected by their owner-scoped IDs from a completed inventory read; the
  response must address the selected pair and their evidence fields.
- Linked-strategy follow-ups lost the selected setup or became broad inventory
  answers. The per-turn contract persists the current question, answer type,
  selected verified objects and evidence; a reference to the previously
  verified pair can reuse that pair without changing objects.
- The answer verifier rejected correct read-only replies due to a second
  semantic pass and overly broad checks for negated order mentions, Dutch
  Markdown tables, field identifiers and general risk mechanics. Factual reads
  and general stop/size explanations now use source-bound checks, while write
  safety and other hard constraints remain in force.
- A transient first Responses error previously ended in a generic failure.
  The loop makes one bounded retry for transient provider errors and records
  safe error type/status diagnostics.

## Local Build Evidence

The disposable parity stack used isolated PostgreSQL, Redis, API and prefork
Celery with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`;
the real-provider selector used its configured `gpt-4o-mini`. No protected QA
fixture or sealed holdout was used.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses conversation regression | `24/24` read-only turns across eight multi-turn sequences, including the exact reported stop/size, BTC/Apple comparison, correction, and linked-strategy follow-up paths. | `.local-finn-parity-artifacts/coach-turn-contract-final-v8.json`, SHA-256 `777e3d53ead1147a9e4f6a9f5e60593af3d0d3a86ef32ada0d663d40c6d79cfd`. |
| Full worker-driven safe action-contract matrix | `16/16`; zero broker orders, live bots, live-trading calls or production connections. | `.local-finn-parity-artifacts/coach-turn-contract-action-final.json`, SHA-256 `4a376399b39413a74e89d44fde33df7311a43a6cf38d6763eb0909d17d37fe0b`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-turn-contract-provider-development.json`, SHA-256 `509f35dd92c8e1aa313d369c88c6159a364845e015c5568e2a6db0c4142a9e1d`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-turn-contract-provider-regression.json`, SHA-256 `1f8f9ca235c222cd47c2aafd0adcb7e740f8d6bf6778130a2923500de67b6a5e`. |
| Backend canonical suite | `2965 passed, 3 skipped` on final source. | `pytest -q --disable-warnings --tb=short`. |
| Frontend canonical checks | Passed; no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, production `build`. |

The additional 37-case nonsealed parity diagnostic completed but reported
`all_passed=false`. Its embedded action chain was `16/16` and lineage `9/9`;
read-only model-led cases did not emit the legacy `final_operation_id` the
runner expects, and terminal p95 was 18.9 seconds against its 10-second
budget. Artifact: `.local-finn-parity-artifacts/coach-turn-contract-action-matrix.json`,
SHA-256 `8ec75248dd096ebcaf9bb2e359c0f8cafcf005efbc9f5f10e6933f0d74abeb2e`.
This diagnostic gap is not presented as a passing result or a QA verdict.

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Backend health and frontend build-info | Pending for this candidate. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Build's local evidence establishes technical readiness for a candidate only.
Authenticated production coach acceptance remains independent QA's
responsibility.
