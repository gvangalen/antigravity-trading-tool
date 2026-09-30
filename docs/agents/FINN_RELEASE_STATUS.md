# FINN Release Status

This is the current status page for the active FINN release. Runtime identity is
verified from Git and the public deployment surfaces, not from this file's own
commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_AWAITING_CI` |
| Active goal | Resolve the three live coach cautions on `2b0b923b2e76e097604991d9982cacf786be77a0`: saved 4H confirmation-rule fallback, stop-loss coach runtime failure, and failure to address an objection to a strict rule |
| Candidate branch | `codex/finn-coach-live-caution` |
| Candidate code SHA | `b5b3a3e4ecea030069752c7428e1e91e7f316bf5` |
| Production SHA | Pending candidate deployment and public SHA verification. The user's preceding live coach run measured backend and frontend at `2b0b923b2e76e097604991d9982cacf786be77a0`. |
| Release owner | Build |
| Last updated | `2026-09-30` |

The user reported a `caution` verdict after 12 authenticated browser turns on
`2b0b923b2e76e097604991d9982cacf786be77a0`: a direct saved-rule question
fell back generically, a stop-loss coach question failed to finish, and FINN
repeated a clarification instead of addressing an objection. This is
user-provided live evidence, not Build's independent QA verdict. The earlier
coach candidate is superseded by this repair batch.

## Local Build Evidence

The synthetic local probes used an isolated Docker Compose project with
PostgreSQL, Redis, API, and Celery. The actual chat and repair route used
`gpt-6-luna` with reasoning `none`; the selector and semantic verifier used
`gpt-4o-mini`. Build did not access the protected production QA fixture or the
QA-exclusive sealed holdout. All artifacts below are local, ignored files under
`.local-finn-parity-artifacts/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused coach regressions | `PASS` | Unit tests cover forced owner-scoped read, verified absence, read-only stop-loss timeout and deadline behavior, strict-rule objection, negated outcome claims, and source-grounded limited reviews. |
| Worker-driven live-caution conversation | `3/3` | `coach-live-caution-targeted-final2.json`, SHA-256 `cf49aec57fb3b289f90c9ffb78824b940a7cf91bb9603fecece6947bd8c72b7f`; each turn completed with one dispatch, polling/SSE parity, and no proposal. |
| Public declassified coach route | `4/4` | `coach-live-caution-public-final2.json`, SHA-256 `755bfe0e0947c40f57ec212ba831d4d4f1ddd37783ec82ceb421caa832a346dc`. |
| Worker-driven personal coach conversation | `8/8` | `coach-live-caution-personal-final2.json`, SHA-256 `d98821953c819e1debd58d1b33fe12ce44207a1e00a605e628787c8892067294`. |
| Worker-driven safe action contracts | `16/16` | `coach-live-caution-action-matrix-final2.json`, SHA-256 `4060178529dbf2d4de2a624ecf385e050a3b982dc44bd3e42dd43b38d13330db`; zero broker orders, live-trading calls, live bots, and production connections. |
| Real-provider selector development | `18/18` | `coach-live-caution-provider-development.json`, SHA-256 `32d384be664cde21aefbc744a8f699288666419487dae090b12590b205f2c23e`. |
| Real-provider selector regression | `109/109` | `coach-live-caution-provider-regression.json`, SHA-256 `82b46cf8375e52b07bd68541b9c1f1d1d868461fbf14a1f128515d7b135cac12`; no provider, schema, parse, or timeout failures. |
| Backend canonical suite | `2873 passed, 3 skipped` | `python3 -m pytest -q` on candidate source. |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high` (zero vulnerabilities), and production `build`. No frontend source changes in this batch. |

The first local attempts exposed a negation false positive in the outcome
boundary and a read-repair deadline race. Both were repaired before the final
runs above. Provider outputs can vary, so authenticated live acceptance remains
independent QA's responsibility.

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PENDING` |
| Auto Deploy | `PENDING` |
| Backend health and frontend build-info | `PENDING` |
| Independent live QA for this candidate | `NOT_STARTED`; only the user assigns it after deployment |

After Auto Deploy, Build verifies only successful deployment, public HTTP
availability, and exact backend/frontend SHA. QA owns the authenticated live
runtime verdict.
