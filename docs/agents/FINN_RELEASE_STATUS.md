# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_VALIDATED`; production deployment pending. |
| Goal | Preserve already supplied fixed and Smart DCA inputs across the first proposal, clarification and retry after a failed turn. |
| Candidate branch | `codex/finn-dca-conversation-recovery` |
| Candidate code SHA | `20252252ae265ec9fc32623c9cbae75ac37caa9d` |
| PR | [#51](https://github.com/gvangalen/antigravity-trading-tool/pull/51), draft at this stage. |
| Production SHA | Pending Auto Deploy and public identity checks. |
| Release owner | Build |
| Last updated | 2026-10-04 |

The user supplied independent, read-only live chat findings on `ea7ca16326217b907e85fb6a1f03e26581df6eb9`: a full Smart DCA request lost its three percentages, “elke 5e van de maand” lost the day, and a failed turn lost the earlier collecting draft. The first two failures were reproduced in the local input parser. The exact cause of the live “FINN kon dit antwoord niet afronden” turn remains unproven without its run trace. Build used only synthetic local users and did not access protected QA fixtures or sealed material.

## Change

- FINN retains all three explicitly stated Smart DCA percentages and a named base amount even when calculated euro amounts also appear.
- Weekly weekdays and ordinal monthly days are collected from the initial DCA request.
- A percentage clarification can fill all three pending bands in one turn. After a failed or unavailable turn, a still collecting owner-scoped draft remains available for retry.
- The score source, paper execution and action confirmation boundaries are unchanged.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider with synthetic users. No production account or live order was used.

| Gate | Result | Evidence |
| --- | --- | --- |
| API/Celery/Responses DCA conversation probe | Exact Smart DCA request and ordinal monthly request each produced a complete proposal in one turn; an incomplete Smart DCA request followed by all three percentages produced a complete proposal. Polling/SSE parity passed; no proposal was confirmed. | `.local-finn-parity-artifacts/dca-conversation-probe.json`, SHA-256 `7f65e80946b7c2ce6cb6591730cd093dae9d79fbeafdf060b37ea6ffd1138275`. |
| Worker-driven safe action contracts | `16/16`; no broker orders, live trading calls or live bots. | `.local-finn-parity-artifacts/dca-conversation-action-matrix.json`, SHA-256 `bf87d415fe35d0344e583afe2040184129e8b9911a0c639b3f32ae401ddde5c5`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-conversation-selector-development.json`, SHA-256 `873612a250af2e15c4a5711eb714b532ab53de1049d01c16f7f7761bad7148fa`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/dca-conversation-selector-regression.json`, SHA-256 `f8eff871774ce9b90bacf50ea2de8d2754a11ed81ec191322a6c9991ad9083a0`. |
| Backend canonical suite | `3060 passed, 3 skipped`. | `python3 -m pytest -q`. |
| Frontend and other CI checks | No frontend source changed; PR CI all five jobs passed on the code SHA. | [PR run 37183857041](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37183857041). |

The failed-turn recovery is covered at the runtime-contract continuation boundary. The specific live provider error was not reproduced locally, so this evidence proves draft recovery after a failed contract, not elimination of every provider failure.

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS` on code SHA: [PR run 37183857041](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37183857041), all five jobs green. Status-only candidate commit requires its own CI. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence and CI do not establish authenticated production acceptance.
