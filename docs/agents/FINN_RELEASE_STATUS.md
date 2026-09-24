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

The current uncommitted repair remains `BUILDING`. Two consecutive local public
Responses conversation gates are `20/20`, including a four-turn conversation,
an owner-scoped draft revision, confirmation, execution, replay, and readback.
The `Waarom?` follow-up now requires `answer_directly` without unrelated reads.
Artifacts: `.local-finn-parity-artifacts/finn-responses-relevance-v18.json`,
SHA-256 `f60f0482bd92f31cd8163ddd046c43c809e6ad93f7c6672ed2471ec3e96b1e8b`,
and `.local-finn-parity-artifacts/finn-responses-relevance-v19.json`,
SHA-256 `eb4dab08e8abd60b12926ab37b1dcd9dd8d69cd257cd4238dc2b7e0acafab43b`.
The latest complete worker-driven action matrix is `16/16` with zero broker,
live-trading, or live-bot effects. Artifact:
`.local-finn-parity-artifacts/finn-responses-action-matrix-v18.json`,
SHA-256 `07042b60143e9968d56ce0e75d3ff0aeeb6524b93c94d0a5e4425a875fd129a3`.
The current backend root suite is `2497 passed, 3 skipped`. The real-provider
development and regression gates were rerun on the final conversation-lineage
code and passed `18/18` and `109/109`, respectively, with zero provider,
schema, parse, validation, or timeout failures. No CI, deployment, or
independent QA has started for this repair.

| Gate | Status | Evidence |
| --- | --- | --- |
| Responses runtime scenarios | `PASS` | Two consecutive public real-provider API runs `20/20` each, including scoped short follow-up and persisted draft lifecycle; artifacts and hashes above. |
| Fresh-owner regression | `PASS` | Public API/Celery guided setup, explicit confirmation, one persisted setup, idempotent replay, and exact saved-name/4H readback with a new owner; `.local-finn-parity-artifacts/finn-responses-fresh-owner-repair.jsonl`, SHA-256 `56195d95ff3ca10507994edfdb46d463a06bda9dc6d58f3019e6a1e54f92b28d`. |
| Action matrix | `PASS` | Current local worker-driven `16/16`, including guided strategy, proposal/confirmation/execution/replay; no broker, live trading or live bot effect; `.local-finn-parity-artifacts/finn-responses-action-matrix-v18.json`, SHA-256 `07042b60143e9968d56ce0e75d3ff0aeeb6524b93c94d0a5e4425a875fd129a3`. |
| Visible Draft Card | `PASS` | Local browser shows a registry-backed BTC DCA proposal with name, timeframe, frequency, amount and explicit confirmation; `/tmp/finn-responses-draft-card-amount-local.png`, SHA-256 `ecf1f84a70f57bf7bbc7f53e481e980e478240ef05c34d64aca52c65d00e819e`. |
| Provider development | `PASS` | Current real provider `18/18`; `.local-finn-parity-artifacts/finn-responses-provider-development-v18.json`, SHA-256 `9bff107bc9db8196eeb53e216b3f162eca658c1dcd01930ac9f71d405e34d3cd`. |
| Provider regression | `PASS` | Current real provider `109/109`; `.local-finn-parity-artifacts/finn-responses-provider-regression-v18.json`, SHA-256 `f4ddeea08184f29518065ebe519e6e69d1b2b8df5cf50b33c52d003447b509ed`. |
| Backend suite | `PASS` | `2497 passed, 3 skipped` from the canonical checkout root. |
| Frontend suite | `PASS` | Current `typecheck` and production build passed; earlier `lint:i18n`, `test:i18n`, `test:commands`, guided-modal, and `audit:high` passed before this backend-only repair. |
| CI | `NOT_RUN` | Awaiting the validated candidate push. |
| Deployment | `NOT_RUN` | Production remains on `258b998a…`; its first safe Build smoke exposed fresh-owner readback defects. The repair candidate has not deployed or run a new live smoke. |
| Official independent QA | `NOT_STARTED` | Build does not initiate official QA. |

## Independent QA

- No independent QA has been started for this candidate.
- The sealed holdout remains QA-exclusive and was not read or used by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
