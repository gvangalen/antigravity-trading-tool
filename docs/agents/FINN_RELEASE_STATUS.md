# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; Build release gates passed. |
| Active goal | Repair the defects from live SHA `71d45f271800d56307d90ee598d78e9f9e88d6a8`: read-only stop-loss coaching fallback, first-turn saved-setup inventory fallback, and failure to resolve “de tweede uit jouw lijst”. |
| Candidate branch | `codex/finn-coach-followup-grounding` ([PR #25](https://github.com/gvangalen/antigravity-trading-tool/pull/25), merged). |
| Candidate code SHA | `d33472f5` (includes `9be63c7c`); merge SHA `9b03ea3de8846d83c88a6dbf5bbee8b5a493aa41`. |
| Production code SHA | `9b03ea3de8846d83c88a6dbf5bbee8b5a493aa41`, verified on public backend health and frontend build-info at 05:37 UTC on 2026-10-01. This status-only follow-up creates another deploy SHA; verify that runtime identity separately. |
| Release owner | Build |
| Last updated | `2026-10-01` |

The prior candidate's release and QA evidence remain in Git history. This is a
new local repair batch. Build did not use the protected production QA fixture
or sealed holdout and did not run authenticated production QA.

## Root Cause and Repair

The exact first-turn question, “Welke BTC-setups staan er op Mijn Plan? Noem de
namen, zonder iets te maken of wijzigen”, was classified as `update` because
the negated clause contains “wijzigen”. The direct rephrase was classified as
`read`. This prevented the typed owner-scoped setup-inventory path from running.
The exact read-only stop-loss coaching question was also classified as
`update` because it says “niet om iets te wijzigen”. The production verifier
reason for its observed fallback is unknown because that live run has no trace;
the incorrect local request polarity is proven, but is not claimed as the sole
production cause.

The preprocessor now treats a negated mutation as a constraint on an explicit
read or coaching request while preserving positive mutation requests. The
Responses front door resolves ordinals from its previously verified ordered
setup list and re-reads the selected owner-scoped setup ID. A bounded read-only
stop-loss recovery provides safe process coaching when a model-led answer
cannot be verified; it never creates a proposal.

## Local Build Evidence

The parity stack used isolated PostgreSQL, Redis, API, and Celery with synthetic
users. Chat used `gpt-6-luna` with reasoning `none`; selection and semantic
verification used `gpt-4o-mini`. Artifacts are ignored files under
`.local-finn-parity-artifacts/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact first-turn setup question, rephrase, then ordinal via API/Celery | `3/3` completed; all three names and the second setup were correct; no proposals. | `exact-inventory-repro.json`, SHA-256 `318b9481f725a0d64f7fd2a5ec00a4d663e71dfe64b408a21cfc35b89b5b5a00`. |
| Stop-loss and list follow-up conversations via API/Celery | `8/8` completed; no proposals. The exact stop-loss prompt received read-only coaching. | `followup-root-probe.json`, SHA-256 `cfa48ab651824ed40f680c740f78f3ef9f6766f4d71074c5c07eca1a09512ba3`. |
| Full safe action-contract matrix on final local build | `16/16`; zero broker orders, live bots, live-trading calls, or production connections. | `coach-ordinal-safe-action-matrix.json`, SHA-256 `3a3e18e67e5e5bb5b1a1ed8419cba5724441d96a56c2d9669fd50e3d55946a37`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, or timeout failures. | `coach-ordinal-provider-development.json`, SHA-256 `f3b9f96e6fbcddff7a2790371d87b9296854b65d235df114429363baef6d3e5b`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, or timeout failures. | `coach-ordinal-provider-regression.json`, SHA-256 `bd702946ac04636e451e90216e2d621b82e462d51f9587ce29978a26f8230ecf`. |
| Backend canonical suite | `2911 passed, 3 skipped`. | `pytest -q --disable-warnings` on final code. |
| Frontend canonical checks | `PASS`; no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, and production `build`. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36820126923`, all five jobs green. |
| Main CI | `PASS`: main run `36820346158`, all five jobs green. |
| Auto Deploy | `PASS`: run `36820494331` deployed merge SHA `9b03ea3de8846d83c88a6dbf5bbee8b5a493aa41`. |
| Backend health and frontend build-info | `PASS`: both HTTP 200 and both reported the merge SHA at 05:37 UTC on 2026-10-01. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Build's local checks establish technical readiness only. Authenticated
production acceptance remains independent QA's responsibility.
