# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILDING` |
| Active goal | FINN Responses Tool Runtime |
| Candidate branch | `codex/finn-responses-tool-runtime` |
| Candidate code SHA | Resolve from the branch commit; this document is not release-authoritative |
| Production SHA | `7d17c0e4d2ff12eb6680b9e0a12ce627b36b4546` (public backend health, 2026-09-23) |
| Release owner | Build |
| Last updated | `2026-09-24` |

## QA Runner

- QA runner readiness: `AVAILABLE`
- authenticated QA preflight: not started for this candidate; Build does not
  access `FINN_QA_USER_ID`.
- official QA status: `NOT_STARTED` for this candidate.

The protected GitHub Actions runner remains the canonical authenticated
production QA executor. This Build batch does not start QA or access its
fixture or sealed manifest. Candidate and live identity must be verified from
Git and deployment surfaces, not from this self-referential status file.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Responses runtime scenarios | `PASS` | Local real-provider public API `15/15`, including zero/one/multiple tools, NL/EN/DE, cross-asset, follow-up, DCA draft revision, confirmation, execution and replay; `/tmp/finn-responses-build-scenarios-v21.json`, SHA-256 `56dedd5d9c503697e26f3e848fbbbfb3cb738d4063ee3086df935c847c67630b`. |
| Action matrix | `PASS` | Local worker-driven `16/16`, including guided strategy and safe proposal/confirmation/execution/replay; no broker, live trading or live bot effect; `/tmp/finn-responses-action-matrix-v21.json`, SHA-256 `0cc3754d22dab547e634e1c19b638ff6e4d2ff8827625d1de37adb190e1fac93`. |
| Visible Draft Card | `PASS` | Local browser shows a registry-backed BTC DCA proposal with name, timeframe, frequency, amount and explicit confirmation; `/tmp/finn-responses-draft-card-amount-local.png`, SHA-256 `ecf1f84a70f57bf7bbc7f53e481e980e478240ef05c34d64aca52c65d00e819e`. |
| Provider development | `PASS` | Real provider `18/18`, no provider or validation failure; `/tmp/finn-responses-provider-development-final.json`, SHA-256 `8e80ea157853aaf64cbf019ee34f5718799f33f27cc4d23deeea00a028516a25`. |
| Provider regression | `PASS` | Real provider `109/109`, no provider, schema, parse, validation or timeout failure; `/tmp/finn-responses-provider-regression-final.json`, SHA-256 `6ff132beff82acdd13a86b73769ed70ad9a9403cbf05f1253d561b81441fd6d9`. |
| Backend suite | `PASS` | `2425 passed, 3 skipped` from the canonical checkout root. |
| Frontend suite | `PASS` | `typecheck`, `lint:i18n`, `test:i18n` (`8/8`), `test:commands` (`5/5`), guided-modal (`5/5`), `audit:high`, and production build passed on the final source. |
| CI | `NOT_RUN` | Awaiting the validated candidate push. |
| Deployment | `NOT_RUN` | Production remains on `7d17c0e4…`; no Build production smoke has started. |
| Official independent QA | `NOT_STARTED` | Build does not initiate official QA. |

## Independent QA

- No independent QA has been started for this candidate.
- The sealed holdout remains QA-exclusive and was not read or used by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
