# FINN Release Status

This page records the current FINN release. Runtime identity comes from Git
and public deployment surfaces, never from this file's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | Repair the three live coach findings on `06a34d7ca9498a89e5d2e2b013b137ac7c3995fe`: identify or disambiguate the saved BTC 4H setup, complete read-only stop-loss coaching, and keep a hypothetical trade reflection out of setup creation. Preserve the working objection follow-up. |
| Candidate branch | `codex/finn-coach-live-followup` ([PR #19](https://github.com/gvangalen/antigravity-trading-tool/pull/19), merged) |
| Candidate code SHA | `c18592d5f23414652db154987c3af499b74e13ab` |
| Production SHA | Code deploy `789f76259978e8081b29e4b90a54cbbad0bb0fd9` verified from public backend health and frontend build-info on 2026-09-30 at 17:34 UTC. This status-only follow-up creates its own SHA, which must be verified after its Auto Deploy. |
| Release owner | Build |
| Last updated | `2026-09-30` |

The user reported a `caution` live browser verdict on the production SHA. One
saved-rule answer omitted which BTC setup it meant; the exact read-only
stop-loss prompt twice failed to finish; and a hypothetical eight-trade
reflection produced a concept setup card after that failure. No account write
was confirmed. The objection and wait-time follow-up worked. These are
user-provided live results, not Build's independent QA verdict.

## Local Build Evidence

The local synthetic fixture uses isolated PostgreSQL, Redis, API, and Celery.
The chat route uses `gpt-6-luna` with reasoning `none`; selector and semantic
verification use `gpt-4o-mini`. Build did not access the protected production
QA fixture or the QA-exclusive sealed holdout. Artifacts are ignored files
under `.local-finn-parity-artifacts/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused coach regressions | `PASS` | Tests cover multi-setup identity, exact stop-loss intent and timeout, hypothetical reflection, action-audit exclusion, previous-context isolation, and the mental-stop safety fallback. |
| Worker-driven exact live prompts | `4/4` | `coach-followup-targeted-priority.json`, SHA-256 `b5ace6f9fe6009c5a02df78959ca5eb7b1f9c7af04f5e1a19170b9a992c0aed2`; same-conversation sequence plus fresh stop-loss turn, one dispatch each, polling/SSE parity, no proposal. |
| Real-provider selector development | `18/18` | `coach-followup-provider-development.json`, SHA-256 `95c1c6688c2cfbcbde9a3d6c2126b10b56c43c15f1f99ed4f224f9ef6a169c9a`. |
| Real-provider selector regression | `109/109` | `coach-followup-provider-regression.json`, SHA-256 `40f11c023d6093967042a53815a7946a4bca4d5a1e4b0fa8926c4bc777b95bee`; zero provider, schema, parse, or timeout failures. |
| Backend canonical suite | `2882 passed, 3 skipped` | `pytest -q` on the current source. |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, and production `build`; no frontend source changes. |
| Worker-driven safe action contracts | `16/16` | `coach-followup-action-matrix-priority.json`, SHA-256 `668c08a876c4b1b44339b4dfafa88629f5a0d683901c9af26b6af738145d71fa`; zero broker orders, live bots, live-trading calls, and production connections. |
| Public declassified coach route | `4/4` | `coach-followup-public-priority.json`, SHA-256 `35de92228e8ed0141527e66b27ccf9f6fb0939a208e05ef1ca2c3c0978105af9`. |
| Personal coach route | `8/8` | `coach-followup-personal-priority.json`, SHA-256 `7326fc1abbb8d94063ec533d2680b5f6f73e5f98ad5be9d99419a6110f4e7d80`. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36751666259` and main run `36751992264`, all five jobs green in each. |
| Auto Deploy | `PASS`: run `36752190095` deployed code merge SHA `789f76259978e8081b29e4b90a54cbbad0bb0fd9`. |
| Backend health and frontend build-info for new candidate | `PASS`: both HTTP 200 and both reported `789f76259978e8081b29e4b90a54cbbad0bb0fd9` at 17:34 UTC. |
| Independent authenticated live QA | Not started; only the user assigns QA after a complete live candidate. |

Build verifies only public availability and deployed SHA after Auto Deploy.
Authenticated production runtime acceptance belongs to independent QA.
