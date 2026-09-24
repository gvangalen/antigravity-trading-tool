# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILD_VALIDATED` |
| Active goal | FINN Responses Tool Runtime |
| Candidate branch | `codex/finn-responses-tool-runtime` |
| Candidate code SHA | Resolve from the branch commit; this document is not release-authoritative |
| Production SHA | `258b998ae19df6a026b63265c507855069ebb82c` (public backend/frontend, 2026-09-24; repair candidate not deployed) |
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
| Responses runtime scenarios | `PASS` | Local real-provider public API `15/15`, including zero/one/multiple tools, NL/EN/DE, cross-asset, follow-up, DCA draft revision, confirmation, execution and replay; `.local-finn-parity-artifacts/finn-responses-build-scenarios-repair-v8.json`, SHA-256 `74068703009cf8288e240e23cb98b1e62a69ecbfb150584f979aa7084fd400e5`. |
| Fresh-owner regression | `PASS` | Public API/Celery guided setup, explicit confirmation, one persisted setup, idempotent replay, and exact saved-name/4H readback with a new owner; `.local-finn-parity-artifacts/finn-responses-fresh-owner-repair.jsonl`, SHA-256 `56195d95ff3ca10507994edfdb46d463a06bda9dc6d58f3019e6a1e54f92b28d`. |
| Action matrix | `PASS` | Local worker-driven `16/16`, including guided strategy and safe proposal/confirmation/execution/replay; no broker, live trading or live bot effect; `.local-finn-parity-artifacts/finn-responses-action-matrix-repair-final.json`, SHA-256 `86051a3c8f174592a227dd121f9cfe833946a99fe6a72d88a8005243429a31cf`. |
| Visible Draft Card | `PASS` | Local browser shows a registry-backed BTC DCA proposal with name, timeframe, frequency, amount and explicit confirmation; `/tmp/finn-responses-draft-card-amount-local.png`, SHA-256 `ecf1f84a70f57bf7bbc7f53e481e980e478240ef05c34d64aca52c65d00e819e`. |
| Provider development | `PASS` | Real provider `18/18`, no provider or validation failure; `.local-finn-parity-artifacts/finn-responses-provider-development-repair.json`, SHA-256 `7c8f3306394f99989da5059aadcc1e692f1a15b56f72bb8007586b6cca4326fa`. |
| Provider regression | `PASS` | A first real-provider measurement was `108/109` on one nondeterministic historical selector case. The exact case passed in isolation, then the complete second run was `109/109` with zero retries or provider/schema/parse/validation/timeout failures; `.local-finn-parity-artifacts/finn-responses-provider-regression-repair-v2.json`, SHA-256 `204e2feed7d951b1e49f5c57f9f52d15ff593007cebc3a55c13ce9ae4cf2eff1`. |
| Backend suite | `PASS` | `2433 passed, 3 skipped` from the canonical checkout root. |
| Frontend suite | `PASS` | `typecheck`, `lint:i18n`, `test:i18n` (`8/8`), `test:commands` (`5/5`), guided-modal (`5/5`), `audit:high`, and production build passed on the final source. |
| CI | `NOT_RUN` | Awaiting the validated candidate push. |
| Deployment | `NOT_RUN` | Production remains on `258b998a…`; its first safe Build smoke exposed fresh-owner readback defects. The repair candidate has not deployed or run a new live smoke. |
| Official independent QA | `NOT_STARTED` | Build does not initiate official QA. |

## Independent QA

- No independent QA has been started for this candidate.
- The sealed holdout remains QA-exclusive and was not read or used by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
