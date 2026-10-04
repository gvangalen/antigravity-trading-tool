# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_CI_PENDING`; local Build gates passed, candidate is not deployed. |
| Goal | Keep a requested setup name separate from follow-up instructions, and replace an open proposal when the user corrects that name. |
| Candidate branch | `codex/finn-dca-name-clarification` |
| Candidate implementation SHA | `203d7951db6d729f25dace37ba9a3521cfc0da19`; followed by this release-status commit. |
| PR | Pending. |
| Production SHA | `5e2ffd25b8ceeb7dc7130936021a71ba30a67f4c`; public backend and frontend both reported it with HTTP 200 on 2026-10-04 before this repair. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- User-provided authenticated live QA on `5e2ffd25b8ceeb7dc7130936021a71ba30a67f4c` found that a requested setup name absorbed “Toon de conceptkaart, bevestig niets”. A subsequent name correction could become a wrong card name or an ordinary chat reply. No card was confirmed; that coach flow was not accepted.
- The typed name collector now separates a named value from later instructions and rejects a bare safety command as a name. An explicit name correction to an open, owner-scoped proposal cancels its old confirmation boundary before building the replacement from the same non-name fields.
- The previously fixed asset clarification remains intact. The corrected flow is asset-agnostic; no asset-specific name rule or coach-answer replacement was added.
- One failed initial ETH proposal in the live QA report had no run-ID or server trace. Eight independent local first-turn proposals succeeded, so the specific cause remains unverified.
- Build used synthetic local users only; no plan, bot or trade was executed. Authenticated production acceptance remains independent QA's responsibility.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector evaluation gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Five-turn ETH → stock → AAPL → name flow | Old ETH proposal withdrawn; AAPL remains selected; the draft name is exactly `Apple DCA Nieuwe QA`; no proposal was confirmed. | `.local-finn-parity-artifacts/proposal-name-followup-summary.json`, SHA-256 `8c51685f898c6e02e8e3ee5cf5f82a4503520dd85065d5a6fe6d075f258ff9f9`. |
| Explicit rename of an open AAPL proposal | Old proposal `cancelled`, old publish HTTP 409; new AAPL draft has only the corrected name. | `.local-finn-parity-artifacts/proposal-rename-result-final.json`, SHA-256 `fc729038bc0a31548edcc03b1bfa19fafe8026bafa11f42146f2b5f32c5062af`. |
| Repeated fresh ETH concepts | `8/8` first-turn drafts on two equivalent phrasings; this does not establish why the isolated live turn failed. | `.local-finn-parity-artifacts/dca-initial-reliability-final.json`, SHA-256 `b4b59826a1d4b05da7491857ee522c4e28873de0206b9584b911e8674c95d504`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/proposal-name-action-matrix.json`, SHA-256 `8ffda9190b9d98f41e3864c96fcc07e3592582f70878dd77069c2f0f28656d72`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/proposal-name-selector-development.json`, SHA-256 `2167fd7b491a94c7fa69964b34ed4e5a2343dcaf8028e930fd27e97f518ed5aa`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/proposal-name-selector-regression.json`, SHA-256 `720efd74a159a0ff7a4e71e22fe4c5913465399612a90f1b0a6a9cf5eca0e7a2`. |
| Backend | `3086 passed, 3 skipped`; includes typed name extraction and proposal correction regressions. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI and Auto Deploy | Pending. |
| Public backend health and frontend build-info | Previous production SHA only; candidate pending. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
