# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | Repair the `caution` live coach findings on `6545eaa25b424ec7ad61d332570a7ccd32c83316bdc`: saved BTC setup names and entry-trigger disambiguation, BTC-to-AAPL rule scope, and unsupported saved-entry claims in hypothetical coaching. |
| Candidate branch | `codex/finn-coach-qa-followup` ([PR #21](https://github.com/gvangalen/antigravity-trading-tool/pull/21), merged) |
| Candidate code SHA | `50bd6a4e58b3c81137cbf1a0623003c2f0a46d28` |
| Production code SHA | `25723c3f732892e83bb8dc249115357a79f16bdc`, verified on public backend health and frontend build-info at 18:41 UTC on 2026-09-30. This status-only follow-up will create another deploy SHA; verify that identity separately. |
| Release owner | Build |
| Last updated | `2026-09-30` |

The user supplied the independent live `caution` findings. Build made no
authenticated production QA run and did not use the protected QA fixture.

## Local Build Evidence

The local parity stack used isolated PostgreSQL, Redis, API, and Celery with
synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`; selector and
semantic verification used `gpt-4o-mini`. Artifacts are ignored files under
`.local-finn-parity-artifacts/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| New coach findings through API/Celery | `4/4` | `coach-qa-followup-probe.json`, SHA-256 `1d59c51b1c2e26a83b3b9dcc9ff53ddca489873838d64ef431de064a18075def`; one dispatch each, polling/SSE parity, no proposals. |
| Prior caution sequence | `4/4` | `coach-qa-followup-old-caution.json`, SHA-256 `64f524bfc6c5160a6424697c7c79d5939ab564213d521fec9e44b1bf6dccbdbb`; includes fresh stop-loss turn. |
| Full safe action matrix | `16/16` | `coach-qa-followup-action-matrix.json`, SHA-256 `91eb2641b2355ca4ff3c439e5c6403ec9d5329cefa39c00ef9c0f2dbdab10ddc`; zero broker orders, live bots, live-trading calls, and production connections. |
| Real-provider selector development | `18/18` | `coach-qa-followup-provider-development.json`, SHA-256 `b56b657f4a32269194c342c3c8e3342c355d901abc0ec34b49e3eb70138a1792`. |
| Real-provider selector regression | `109/109` | `coach-qa-followup-provider-regression.json`, SHA-256 `da0b592158c2d38ca513027c99096f2557893cc36ed3a0546a96005c9898183b`; zero provider, schema, parse, or timeout failures. |
| Backend canonical suite | `2887 passed, 3 skipped` | `pytest -q` on final candidate source. |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, and production `build`; no frontend source changes. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36759675393`, all five jobs green. |
| Main CI | `PASS`: main run `36759916613`, all five jobs green. |
| Auto Deploy | `PASS`: run `36760127235` deployed merge SHA `25723c3f732892e83bb8dc249115357a79f16bdc`. |
| Backend health and frontend build-info | `PASS`: both HTTP 200 and both reported the merge SHA at 18:41 UTC on 2026-09-30. |
| Independent authenticated live QA | Pending; QA owns the protected fixture, full live matrix, and final verdict. |

Build's checks establish a release candidate and deployment identity. The
authenticated production verdict remains independent QA's responsibility.
