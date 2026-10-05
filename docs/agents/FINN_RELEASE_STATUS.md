# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LOCAL_VALIDATED`; candidate CI and deployment pending. |
| Goal | Give each setup an optional, user-written rationale and make it available as owner-scoped FINN coaching context. |
| Candidate branch | `codex/finn-setup-thesis` |
| Candidate implementation SHA | `2829fa42ab4e22b9be10b9afe3a242776676f3aa`; status commits follow it. |
| Production SHA | Pending. |
| Release owner | Build |
| Last updated | 2026-10-05 |

## Change And Limits

- The setup form in My Plan and onboarding offers an optional, 1,000-character text field explaining the idea behind that specific setup. The text appears on its card and loads in the editor for later changes.
- The field uses the existing owner-scoped `setups.description` column. No database migration is needed. The setup API validates length and type on create and update.
- FINN's active-setup and saved-setup inventory tools now expose the description as user-written context. It is not a verified entry trigger, strategy rule, market observation, or order permission.
- The existing trader-context field remains separate: that describes the person; this field describes one setup.
- This change covers manual setup create/edit and FINN read/coach routes. It does not add a natural-language FINN action for writing the rationale.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Owner-scoped setup runtime | Authenticated local create/read/update returned HTTP 200; a second user received HTTP 404; FINN cited the saved rationale and said it was not a proven entry rule. | `.local-finn-parity-artifacts/setup-description-probe.json`, SHA-256 `e900b1894f13966a36ba1cb7d2991bafbc8352d4d3d451f669ee91b59d9b8a73`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/setup-description-action-matrix.json`, SHA-256 `9ca358fc5832a3bc998208a9e49119c45dfcdf784e4b5991f03c250197b7fb13`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-description-selector-development.json`, SHA-256 `e67868df056ffd5c12c75d5f7e9edfb413937be61d03c8f45ea024cb578415f9`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-description-selector-regression.json`, SHA-256 `9aa556e52200875f2ec6decf081006ebbd4e978f871cd7d2f4e4c0fb1193a3b3`. |
| Backend | `3103 passed, 3 skipped`; includes length validation and typed setup evidence. | `pytest -q --disable-warnings`; `.local-finn-parity-artifacts/setup-description-pytest.log`, SHA-256 `cee9e3f7c54c3714d8bb7cd27af6a2f47b304dad4273b134939fc784a0c20c50`. |
| Frontend | Typecheck, i18n lint and tests, command/proposal/setup tests, build and high-severity audit passed; zero high production dependency vulnerabilities. | Local `npm` commands in `frontend/trading-tool-frontend`; generated `out/` is committed. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI and Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
