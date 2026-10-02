# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; required local Build, CI and deployment identity gates passed. |
| Active goal | Keep FINN's read-only coach answer model-owned while binding selected saved setups, linked strategies, and direct follow-up evidence to owner-scoped reads. Prevent valid comparisons and general risk explanations from being erased by unrelated verifier checks. |
| Candidate branch | `codex/finn-coach-evidence-flow` |
| Candidate code SHA | `3fec0753374b673e6879df114987d69df39f1e51` |
| Candidate PR/head SHA | [PR #37](https://github.com/gvangalen/antigravity-trading-tool/pull/37), head `1f7b6db3d4c1782f76b00f07a0d07da7051504d0`, merged. |
| Production code SHA | `61177edc510f53603d787354383f15deb5199533`; public backend health and frontend build-info both returned HTTP 200 and this SHA at 06:10 UTC on 2026-10-02. This status-only follow-up creates another deploy SHA; verify that runtime identity separately. |
| Release owner | Build |
| Last updated | 2026-10-02 |

The earlier `codex/finn-single-owner-flow` candidate and its status-only merge
reached production, but the user's authenticated live coach test on
`34915e27ec9b9a8c589b10198f97c4973cccac8c` found further continuation
failures. This repair batch supersedes that candidate. Build has not run
protected QA fixture tests or the sealed holdout. Independent authenticated
production QA remains pending and user-owned.

## Root Causes And Repair

- A two-setup inventory read returned the correct pair but omitted their
  linked strategies. FINN now reads both selected owner-scoped setups and
  reports each strategy's availability in the same typed tool result. Luna
  still composes the comparison.
- A direct question about a just-read strategy lost its evidence at the next
  turn. The turn contract and deterministic numeric checks now reuse only the
  previous verified read for the same owner-bound setup.
- The answer verifier misread saved stop-distance percentages as price levels,
  and treated a read-only lookup or negated write as a performed write. These
  checks now distinguish static arithmetic and readback from mutation claims.
- A repeated read could exhaust the tool round limit after evidence was
  already available. In model-led coaching a duplicate completed read now
  ends the tool phase so Luna can answer or state the limit.
- A direct follow-up about the stop-distance/position-size tradeoff could lose
  the position-size topic. The turn contract preserves both subjects when the
  user explicitly continues that tradeoff.

## Local Build Evidence

The disposable parity stack used isolated PostgreSQL, Redis, API and prefork
Celery with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`.
The selector evaluation used its configured `gpt-4o-mini`; this batch does not
claim a migration of every safety or selector model. No production account was
written by these tests.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses coach regression | `35/35` read-only turns across 12 complete conversations; one dispatch per turn, no proposal or write. Includes the latest live-QA failure sequence. | `.local-finn-parity-artifacts/coach-evidence-all-r7.json`, SHA-256 `26a85666369178bc89e11a6433090638a2dceb1b0fffa9bc575c0c44212f2e6c`. |
| Full worker-driven safe action-contract matrix | `16/16`; zero broker orders, live bots, live-trading calls or production connections. | `.local-finn-parity-artifacts/coach-evidence-action-matrix.json`, SHA-256 `1ab830480ca50085bf32e6ace06ba80d51ef2bed6535feb444894b9405b4c5fb`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-evidence-provider-development.json`, SHA-256 `d10da496f8f358527aeeece43aaf24c5a08a9fe58b7ab353b32ebc9b7bc043b2`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-evidence-provider-regression.json`, SHA-256 `60bbc4c22af296957f29ad15efff6b0fa515dea51ed8d487550eae45025981e0`. |
| Backend canonical suite | `2982 passed, 3 skipped`. | `pytest -q --disable-warnings --tb=short`. |
| Frontend canonical checks | Passed, with no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, production `build`. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36971813009`, all five jobs green on head `1f7b6db3d4c1782f76b00f07a0d07da7051504d0`. |
| Main CI | `PASS`: main run `36972004101`, all five jobs green on merge SHA `61177edc510f53603d787354383f15deb5199533`. |
| Auto Deploy | `PASS`: run `36972151434` deployed merge SHA `61177edc510f53603d787354383f15deb5199533`. |
| Backend health and frontend build-info on candidate SHA | `PASS`: both HTTP 200 and both reported the merge SHA at 06:10 UTC on 2026-10-02. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and final verdict. |

Build's local and deployment evidence establishes technical readiness only.
Authenticated production coach acceptance remains independent QA's
responsibility.
