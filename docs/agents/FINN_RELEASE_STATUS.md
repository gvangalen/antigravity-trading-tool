# FINN Release Status

This is the current status page for the active FINN release. Runtime identity is
verified from Git and the public deployment surfaces, not from this file's own
commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA` |
| Active goal | FINN Responses Tool Runtime with `gpt-6-luna`, reasoning `none` as the chat default |
| Candidate branch | `codex/finn-responses-tool-runtime` |
| Candidate code SHA | `7de58a867f423d40efd9ed5573a34ad41ab573af` ([PR #12](https://github.com/gvangalen/antigravity-trading-tool/pull/12)) |
| Production SHA | Read the live backend health and frontend build-info. The status-only commit that records this release has its own SHA, so this file cannot identify that commit in advance. |
| Release owner | Build |
| Last updated | `2026-09-30` |

## Local Build Evidence

All runs below used synthetic local owners, the real Responses provider, the
local API, persisted worker lifecycle, polling, and SSE where applicable. The
local parity runtime reports `gpt-6-luna` for chat, clarification, and repair,
with reasoning `none`. The independent semantic verifier remains
`gpt-4o-mini`. The candidate's production PM2 config sets the Luna defaults for the API and all
workers, including when an old PM2 process environment carries stale values.

| Gate | Result | Evidence |
| --- | --- | --- |
| Dutch coaching conversation | `8/8` | `.local-finn-parity-artifacts/coach-luna-release-final-nl-v7.json`, SHA-256 `9a5056129e9808ef347bd0f9c311020f57c8843aef7a5bd45019658ebb1adb03` |
| Alternate Dutch conversation | `4/4` | `.local-finn-parity-artifacts/coach-luna-release-final-alt-nl-v7.json`, SHA-256 `41d0ffa59f6006bbd75495bc3570dac012bc34a01b22cb8a4240e0659a47bf4e` |
| Alternate English conversation | `4/4` | `.local-finn-parity-artifacts/coach-luna-release-final-alt-en-v7.json`, SHA-256 `4a40ccbe63455f4d1bd88136cbe5f0e4db52965e964ab797d32e4375d6bd4304` |
| Action contract matrix | `16/16` | `.local-finn-parity-artifacts/action-matrix-luna-release-final-v8.json`, SHA-256 `c217e1fa1cc1eb902bc078e6da4a37d3ee7c5ab9d594bb749cb68d3d2fac10fc`; zero broker orders, live-trading calls, or live bots. The preceding `15/16` run exposed a four-second action-alignment timeout, corrected before this run. |
| Real-provider selector development | `18/18` | `.local-finn-parity-artifacts/luna-release-provider-development.json`, SHA-256 `226e10d6091db692a0aed5f13e9a0bece4cbd693a79250e77ff5138e01f6a374` |
| Real-provider selector regression | `109/109` | `.local-finn-parity-artifacts/luna-release-provider-regression.json`, SHA-256 `51ffc2ef9f9aea166478b2e290a42b97172cabc04b2cf2c84091990d7f33e542` |
| Backend root suite | `2847 passed, 3 skipped` | `pytest -q` on the current working tree |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high` (zero high vulnerabilities), and production `build` |
| Production PM2 model defaults | `PASS` | Node check of all five production app environments, including a simulated stale model and reasoning process environment |

The public 48-case legacy operation-ID diagnostic ran before the last repairs
and scored `10/48`: `.local-finn-parity-artifacts/public-48-luna-release.json`,
SHA-256 `57caabeb800c3becc5447d4523df0db907f31d08e5357980aba4c2728527983a`.
Its operation-ID assertions target the old selector route and do not describe
the direct Responses chat contract. This is a recorded red diagnostic, not a
claim of 48-case parity; the current action contract matrix remains the
canonical Build action gate. The diagnostic also exposed read/language defects
that were fixed and covered by focused regressions and the conversations above.

## Release and Independent QA

| Gate | Status |
| --- | --- |
| CI | `PASS`: PR run `36674086375` and main run `36674335437`, all five jobs green for code SHA `7de58a86…` |
| Auto Deploy | `PASS`: run `36674476178` deployed code SHA `7de58a86…` |
| Backend health and frontend build-info for candidate | `PASS`: both HTTP 200 and both reported `7de58a867f423d40efd9ed5573a34ad41ab573af` after Auto Deploy on 2026-09-30 |
| Official independent QA | `NOT_STARTED`; Build has not accessed the QA fixture or sealed holdout |

Only the user assigns independent production QA after Build records a complete
live candidate. Build does not start, instruct, or contact QA.
