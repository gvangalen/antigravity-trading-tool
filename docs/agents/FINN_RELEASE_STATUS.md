# FINN Release Status

This is the current status page for the active FINN release. Runtime identity is
verified from Git and the public deployment surfaces, not from this file's own
commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LOCAL_VALIDATED_AWAITING_CI` |
| Active goal | Correct Paper-bot concept names and per-bot budget readback after the live browser caution verdict |
| Candidate branch | `codex/finn-bot-budget-readback` |
| Candidate code SHA | `493afb696f609dcda5ac6868a4a10e77ea89118e` |
| Production SHA before this candidate | `730319fb5ef91a272cf4c8ff58d9e7fff7fe32f3` |
| Release owner | Build |
| Last updated | `2026-09-30` |

The user-reported live browser run on `730319fb…` passed the setup, strategy,
Paper-bot, watchlist, and coaching flows but returned `caution`: the first bot
concept included its budget phrase in the name, and a later readback called
€600 a portfolio limit while denying a separate bot budget. The test account's
Analysis onboarding prevented independent overview-page checks. That run did
not prove the model name used by production.

## Local Build Evidence

All local runtime probes below used a new isolated Docker Compose project,
synthetic users, a local PostgreSQL/Redis/API/Celery stack, and the real
Responses provider. The stack explicitly reported `gpt-6-luna` for chat,
clarification, and repair with reasoning `none`; the independent selector and
semantic verifier retain `gpt-4o-mini`. Build did not access the protected QA
fixture or sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Bot concept and budget regressions | `PASS` | The model-suggested name drops the trailing budget clause; the portfolio schema and read output include each owner-scoped bot's `budget_total_eur`. |
| Worker-driven safe action contracts | `16/16` | `.local-finn-parity-artifacts/bot-budget-action-matrix.json`, SHA-256 `a157d50fb57bf5f26a1144f61c1fcc4e6f61df5c6008e12178ff4d277096b0c8`; zero broker orders, live-trading calls, or live bots. |
| Affected bot action/readback chain | `PASS` | `.local-finn-parity-artifacts/bot-budget-live-regression.json`, SHA-256 `a613e893f3dd7f4d0a5595356e9f9f2b07f4633810c9ccf3c4e77bd425e6534c`; create at €500 with the exact name, confirm and execute, update to €600, confirm and execute, then read the named bot budget as €600 through `get_portfolio_and_exposure` with polling/SSE parity. Both persisted states remained Paper. |
| Real-provider selector development | `18/18` | `.local-finn-parity-artifacts/bot-budget-provider-development.json`, SHA-256 `72fd431ccca9254d97b6be5633433aafa463ffa73b778486798dfa62ddaec9ad`. |
| Real-provider selector regression | `109/109` on rerun | `.local-finn-parity-artifacts/bot-budget-provider-regression-rerun.json`, SHA-256 `1481dd2a1d8a98e0715bafc2562c26d12e42e23ea259727e5024ecaad8646bca`. The first run scored `108/109` (SHA-256 `361b7003dd90e1b0bf98f136015451adc9de0c00dd94bab6bd7930e323cc41fc`): a plan-risk question was once classified as `evaluate_setup` instead of `evaluate_plan`. Three isolated retries gave `evaluate_plan` twice and `evaluate_setup` once. This selector variance remains an open risk outside the bot change. |
| Backend canonical suite | `2849 passed, 3 skipped` | `python3 -m pytest -q` on this candidate's source tree. |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high` (zero high vulnerabilities), and production `build`; frontend source did not change. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PENDING` |
| Auto Deploy | `PENDING`; production remains on `730319fb…` |
| Backend health and frontend build-info for this candidate | `PENDING` |
| Independent live QA for this candidate | `NOT_STARTED`; only the user assigns it after deployment |

Build will verify only Auto Deploy success, public HTTP availability, and exact
backend/frontend SHA after deployment. QA owns the independent live runtime
verdict after the user assigns that work.
