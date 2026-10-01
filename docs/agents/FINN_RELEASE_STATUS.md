# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; required local Build, CI and deployment identity gates passed. |
| Active goal | Repair FINN's recurring coach continuation failures as one flow: inconsistent saved-setup inventory, ordinal and pronoun references, wrong linked-strategy levels, coach turns becoming inventory answers, BTC-to-Apple rule transfer, and generic failure after a source-bound follow-up. |
| Candidate branch | `codex/finn-coach-context-contract` ([PR #31](https://github.com/gvangalen/antigravity-trading-tool/pull/31), merged). |
| Candidate code SHA | `299efd3fbaab4b9175040e8fc5c400450b008bd4`. |
| Candidate PR/head SHA | `d3ddddff2e8c044542ff3ae82535b03287649921`. |
| Production code SHA | `2c0423a93cab418071042a9150608cd5419abffd`, verified on public backend health and frontend build-info at 13:26 UTC on 2026-10-01. This status-only follow-up creates another deploy SHA; verify that runtime identity separately. |
| Release owner | Build |
| Last updated | `2026-10-01` |

The previous release status at base SHA `107e9b30286bd7784681e1269e7ea613ef0e60bf`
was `READY_FOR_INDEPENDENT_QA`, but the user reported further related coach
failures. No official independent QA run for this new candidate has started.

## Root Causes and Repair

- The Responses inventory read existed, but its name was absent from the
  persisted tool-envelope schema and the canonical tool-to-scope map. Its
  evidence ingestion failed. The schema now accepts that owner-scoped read and
  binds it to the existing setup scope. Payload models are selected by their
  explicit schema name before validation; permissive union parsing could
  otherwise silently discard inventory fields.
- A setup named in a completed owner-scoped read now becomes a typed subject
  in the runtime contract. Ordinals and conversational references resolve
  against that verified subject, and subsequent reads re-fetch its ID. The
  subject is cleared on a plural inventory, an asset switch, or an unverified
  topic change. A model-supplied setup name cannot select a different record.
- The answer verifier checks saved price levels against the selected setup's
  linked strategy, including compact numeric pairs. A rejected model answer
  can use a source-bound readback only when the selected setup and linked
  strategy agree. Unclear cross-asset transfers ask for the source and target;
  explicit BTC-to-Apple transfers state that the BTC rule does not apply
  automatically.
- A verified single-setup continuation bypasses a redundant broad-inventory
  classifier. This avoids both a list misroute and an unnecessary provider
  round that previously consumed the visible lifecycle deadline. Hypothetical
  first-person market questions remain read-only; direct order requests keep
  the execution boundary.
- Broad diagnoses of a trader's approach are typed as aggregate plan
  evaluations. The raw selector's first final-code regression attempt had one
  `evaluate_setup` choice for this meaning (108/109); the grammar correction
  makes the live route deterministic, and the repeated full real-provider
  regression passed 109/109. Both results are retained as measured evidence.

## Local Build Evidence

The disposable parity stack used isolated PostgreSQL, Redis, API and Celery
with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`;
the real-provider selector evaluation used its configured `gpt-4o-mini`.
No protected QA fixture or sealed holdout was used.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery conversation regression | `12/12` read-only turns across four sequences, including list → second setup → strategy levels → coach turn → strategy levels; no proposals or writes. | `.local-finn-parity-artifacts/coach-context-runtime-final.json`, SHA-256 `ee32a86ff7090bdc4f9c13b89610280d278f7fe649a19217c0e2cb2a9aae797e`. |
| Full worker-driven safe action-contract matrix | `16/16`; zero broker orders, live bots, live-trading calls, or production connections. | `.local-finn-parity-artifacts/coach-context-action-matrix-final.json`, SHA-256 `7e2e207aef08ec4736f4f3946caee43573ebccb74936e9021de7e27ff74c8c69`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-context-provider-development-final.json`, SHA-256 `9977cbdbebd30c319006151aff2f01966a0cf9aab53ad074e566dd43d1be25df`. |
| Real-provider selector regression | Final repeat `109/109`; zero provider, schema, parse, validation or timeout failures. Prior attempt `108/109` on the pre-grammar version is recorded above. | `.local-finn-parity-artifacts/coach-context-provider-regression-final-v3.json`, SHA-256 `f81c79177acab53076275bbf54f8ee40170fe230c097978cbb7148ab34933f61`. |
| Backend canonical suite | `2950 passed, 3 skipped` on final source. | `pytest -q --disable-warnings`. |
| Frontend canonical checks | Passed; no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, production `build`. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36868064043`, all five jobs green. |
| Main CI | `PASS`: main run `36868314477`, all five jobs green. |
| Auto Deploy | `PASS`: run `36868558103` deployed merge SHA `2c0423a93cab418071042a9150608cd5419abffd`. |
| Backend health and frontend build-info | `PASS`: both HTTP 200 and both reported the merge SHA at 13:26 UTC on 2026-10-01. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Build's local evidence establishes technical readiness only. Authenticated
production coach acceptance remains independent QA's responsibility.
