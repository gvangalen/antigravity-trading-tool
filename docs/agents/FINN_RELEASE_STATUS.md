# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; required local Build, CI and deployment identity gates passed. |
| Active goal | Make FINN's read-only coach conversation model-owned: Luna chooses reads and composes the answer; the server binds only owner-scoped objects, checks source claims and write safety, and returns structured rejection for one model repair. Verify complete multi-turn conversations. |
| Candidate branch | `codex/finn-single-owner-flow`. |
| Candidate code SHA | `b737aa83d4b11fb76813d73fa4d6960d7e08eb39`. |
| Candidate PR/head SHA | [PR #35](https://github.com/gvangalen/antigravity-trading-tool/pull/35), head `b5f1664a6d1cfcc2a5b7948ed52a59584d832bb3`, merged. |
| Production code SHA | `4772960646257870889b8955ceb25b1ed31281e9`, verified on public backend health and frontend build-info at 22:13 UTC on 2026-10-01. This status-only follow-up creates another deploy SHA; verify that runtime identity separately. |
| Release owner | Build |
| Last updated | `2026-10-02` |

The previous candidate on `codex/finn-turn-contract` reached
`READY_FOR_INDEPENDENT_QA` but the user reported further related live failures.
It is superseded by this batch. No independent QA run has started for this
new candidate.

## Root Causes and Repair

- The chat route still included legacy collection and answer-sufficiency
  decisions that could turn the current question into an inventory or fixed
  response. The production run now enables the model-led path explicitly.
  Luna chooses a read when needed and composes the answer; explicit read-only
  coaching turns cannot call proposal tools.
- Multi-object reads could use one asset/timeframe filter or a model-supplied
  name as authority. The server now binds at most two selected names to
  owner-scoped inventory IDs and the current user request or a verified prior
  subject. A complete inventory or an unbound general tradeoff has a bounded
  read path, avoiding repeated unrelated account lookups.
- The answer verifier could replace a good answer with fixed coach copy or a
  generic fallback after a second semantic verdict. The model-led path treats
  replacement as structured rejection and gives Luna one repair. Factual
  saved-object reads and asset-transfer boundaries use typed source checks;
  saved numbers, object identity, language and mutation safety remain checked.
- Previous tests exercised individual reads and answers more than their
  continuation. Eight full synthetic conversations now cover ordinal
  references, correct linked-strategy levels, FOMO and asset transfer,
  stop-distance versus position size, two-setup comparisons, corrections and
  strategy readback through the public local API and Celery worker.

## Local Build Evidence

The disposable parity stack used isolated PostgreSQL, Redis, API and prefork
Celery with synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`.
The real-provider selector evaluation used its configured `gpt-4o-mini`; this
batch does not claim a migration of every safety or selector model. No
protected QA fixture or sealed holdout was used.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses conversation regression | `24/24` read-only turns across eight multi-turn sequences; every turn completed in one dispatch with no proposal. | `.local-finn-parity-artifacts/single-owner-all-green.json`, SHA-256 `c50c0ba694245765a6579d422581703748f32832b17ed9557605b0509f5cbbe4`. |
| Full worker-driven safe action-contract matrix | `16/16`; zero broker orders, live bots, live-trading calls or production connections. | `.local-finn-parity-artifacts/single-owner-action-final.json`, SHA-256 `fdd8fc62b925a717ff25280370931a26666c21dffa3b263b184e30e617cea79a`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/single-owner-provider-development.json`, SHA-256 `3758d7dda9ca4daabd93167d68cca252f24f23e958e3e7383c0f0131515d16c3`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/single-owner-provider-regression.json`, SHA-256 `3de05e419ffff9d82269288376b340ce440deacc477e5a3535eaba3a3c2aa829`. |
| Backend canonical suite | `2979 passed, 3 skipped`. | `pytest -q --disable-warnings --tb=short`. |
| Frontend canonical checks | Passed, with no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, production `build`. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36933101250`, all five jobs green on head `b5f1664a6d1cfcc2a5b7948ed52a59584d832bb3`. |
| Main CI | `PASS`: main run `36933335821`, all five jobs green on merge SHA `4772960646257870889b8955ceb25b1ed31281e9`. |
| Auto Deploy | `PASS`: run `36933540084` deployed merge SHA `4772960646257870889b8955ceb25b1ed31281e9`. |
| Backend health and frontend build-info | `PASS`: both HTTP 200 and both reported the merge SHA at 22:13 UTC on 2026-10-01. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and final verdict. |

Build's local and deployment evidence establishes technical readiness only.
Authenticated production coach acceptance remains independent QA's
responsibility.
