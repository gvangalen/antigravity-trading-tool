# FINN Release Status

This is the only current status page for the active FINN release. Keep it
short; link artifacts rather than copying reports or chat history.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `BUILD_VALIDATED` |
| Active goal | FINN targeted presentation and cross-surface context repair |
| Candidate branch | `codex/finn-74ea-targeted-visible-repair` |
| Candidate code SHA | `929062b3ea01a76b15c0b9bce48dab62cccc699a` |
| Production SHA | `74ea7bdc91f6dda3d113a3d444fe44458e2fca43` |
| Release owner | Build |
| Last updated | `2026-09-18` |

## QA Runner

- QA runner readiness: `AVAILABLE`
- authenticated QA preflight: not started for this candidate; Build does not
  access `FINN_QA_USER_ID`.
- official QA status: `NOT_STARTED` for this candidate.

The protected GitHub Actions runner is the canonical authenticated production
QA executor. The candidate adds encrypted QA-owned manifest intake and an
explicit safe-fixture action boundary. The active QA goal supplies the full
SHA; its preflight must prove that the production checkout, release marker,
backend health, and frontend build-info all match it. This avoids treating a
committed status file as a self-referential release marker.

## Evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Targeted worker-driven browser flow | `PASS` | Visible Setup → Strategy → Paper-Bot, cross-surface target/readback, FINN Today, cancel/confirm, refresh/relogin, and cleanup passed. Evidence `/tmp/FINN_TARGETED_VISIBLE_REPAIR_FINAL.json`, SHA-256 `ccb28ecd91dfd0b2b2ff8fa8babd75f02a1d242ca6dcade027fcc06dd57c89f7`. |
| Provider development | `PASS` | Real provider `18/18`; artifact `/tmp/finn-74ea-targeted-provider-development-final-v3.json`, SHA-256 `9f0b21b07979213e3616de2ee94f49b5597c0a7710c71634dc7fffc842eb26ce`. |
| Provider regression | `PASS` | Real provider `109/109`; provider/schema/parse/validation/timeout failures `0`. Artifact `/tmp/finn-74ea-targeted-provider-regression-final-v3.json`, SHA-256 `2a9e2f53c3697e79a50d0ed923f956e218ee0274bf2df2d068a6df9a662e8245`. |
| Backend suite | `PASS` | `2169 passed, 3 skipped` from the canonical checkout root. |
| Frontend suite | `PASS` | `typecheck`, `lint:i18n`, `test:i18n` (`7/7`), `test:commands` (`5/5`), `audit:high`, and production build passed. |
| CI | `NOT_RUN` | Awaiting the validated candidate push. |
| Deployment | `NOT_RUN` | Production remains on the prior release until Auto Deploy completes. |
| Official independent QA | `NOT_STARTED` | Build does not initiate official QA. |

## Independent QA

- No independent QA has been started for this candidate.
- The sealed holdout remains QA-exclusive and was not read or used by Build.

## Allowed Phases

`BUILDING`, `BUILD_VALIDATED`, `DEPLOYING`, `LIVE_SMOKE_RUNNING`,
`READY_FOR_INDEPENDENT_QA`, `QA_RUNNING`, `ACCEPTED`, `NOT_ACCEPTED`.
