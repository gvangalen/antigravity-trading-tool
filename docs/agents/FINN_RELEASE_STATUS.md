# FINN Release Status

This is the current status page for the active FINN release. Runtime identity is
verified from Git and the public deployment surfaces, not from this file's own
commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | Resolve the live coach caution findings: inconsistent FOMO/frustration fallback, unsupported personal confirmation condition, and literal Markdown markers in chat |
| Candidate branch | `codex/finn-coach-consistency` ([PR #15](https://github.com/gvangalen/antigravity-trading-tool/pull/15), merged) |
| Candidate code SHA | `f89187a902319f0b2d0f3813b88b021c8342c178` |
| Production SHA | Read the public backend health and frontend build-info. This status-only follow-up has its own SHA, so this file cannot identify that SHA in advance. |
| Release owner | Build |
| Last updated | `2026-09-30` |

The user reported a `caution` coach verdict from 12 authenticated browser turns on
older SHA `730319fb5ef91a272cf4c8ff58d9e7fff7fe32f3`: two emotional
questions received a generic evidence refusal, FINN referred to a confirmation
condition absent from the active setup, and chat displayed literal `**`.
That browser run is user-provided evidence, not Build's independent QA verdict.

## Local Build Evidence

The local runtime probes used an isolated Docker Compose project with synthetic
users, PostgreSQL, Redis, API and Celery. The actual Responses route used
`gpt-6-luna` with reasoning `none` for chat and repair. The independent
selector and semantic verifier remained on `gpt-4o-mini`. Build did not access
the protected production QA fixture or sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused coach regressions | `PASS` | Deterministic tests cover emotional fallback after semantic and condition-bypass rejection, unsaved confirmation phrasing, source-grounded static risk ratios, horizon clarification and follow-up, and explicit attribution of a user-proposed amount. |
| Worker-driven personal coach conversation | `8/8` | `.local-finn-parity-artifacts/coach-consistency-personal-final-green.json`, SHA-256 `3826cfe87db8ce031e1e047b7ef94328532997d974068731009ba69f120e29cd`. |
| Final focused horizon/FOMO route | `5/5` | `.local-finn-parity-artifacts/coach-consistency-horizon-candidate.json`, SHA-256 `e75fca06a6088cc7517b91aa5e2cb42fe98662c3dc9c2f428c77dce4c323f40f`. This rerun covers the last verifier changes after the 8-turn run. |
| Public declassified coach route | `4/4` | `.local-finn-parity-artifacts/coach-consistency-public-candidate.json`, SHA-256 `3e42c035063471665b0e41e1b0ffef6d7b845145c7529da6696f1969677c6fdd`. |
| Worker-driven safe action contracts | `16/16` | `.local-finn-parity-artifacts/coach-consistency-action-matrix-candidate.json`, SHA-256 `0a3ea3789e7000702e28ac6994c64f54c02ac5ad4abe1f28121d94659990d261`; zero broker orders, live-trading calls, live bots, or production connections. |
| Real-provider selector development | `18/18` | `.local-finn-parity-artifacts/coach-consistency-provider-development.json`, SHA-256 `3aa88b7b2b22551aa77ddf064cd0228792945fc871bfcb2a7cd843d441c1b5a2`. |
| Real-provider selector regression | `109/109` | `.local-finn-parity-artifacts/coach-consistency-provider-regression.json`, SHA-256 `4bd3053baf18a4152f644f96dd2b95ac65b2c39c2b3d3f762fc0030daae87b0a`. |
| Backend canonical suite | `2864 passed, 3 skipped` | `python3 -m pytest -q` on the candidate source tree. |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, chat text parser tests, `audit:high` (zero vulnerabilities), and production `build` with updated tracked `out/`. |

Intermediate local probes exposed verifier wording and provider variance. They
were repaired within this batch; the final route runs above are the release
evidence. Provider output remains variable, so authenticated live acceptance
still belongs to independent QA.

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36705455469` and main run `36705722738`, all five jobs green. |
| Auto Deploy | `PASS`: run `36705921878` deployed code merge SHA `289c28b50019740e5652c56b1329d4f8019fe1a4`. |
| Backend health and frontend build-info for code deploy | `PASS`: both HTTP 200 and both reported `289c28b50019740e5652c56b1329d4f8019fe1a4` on `2026-09-30`. |
| Independent live QA for this candidate | `NOT_STARTED`; only the user assigns it after deployment |

After Auto Deploy, Build verifies only successful deployment, public HTTP
availability and exact backend/frontend SHA. QA owns the authenticated live
runtime verdict.
