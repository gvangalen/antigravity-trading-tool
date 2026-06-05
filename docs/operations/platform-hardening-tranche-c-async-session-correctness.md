# Platform Hardening Tranche C — Async Session Correctness

Last updated: 2026-06-05

## Goal

Remove remaining request paths that can drive one shared SQLAlchemy `AsyncSession`
through concurrent awaits.

This tranche focuses on the known class of failures where service code uses
`asyncio.gather()` across repository calls that share one request/session
boundary.

## What Changed

Implemented in the current working tree:

- `DashboardService.get_dashboard_data()` no longer parallelizes four DB reads
  through one shared session
- `AiAssistantService._build_context()` no longer uses `asyncio.gather()` for
  decision, coach, or analysis context reads that share repository/session state
- platform hardening tests now explicitly guard:
  - mobile overview remains sequential
  - dashboard reads remain sequential
  - assistant context building remains sequential
- deploy wrapper expectations were aligned with the current deploy structure:
  `deploy_live.sh` stays thin while health/deep-health checks live in
  `ops/deploy/deploy_env.sh`

## Primary Touchpoints

- [backend/trading-tool-backend/backend/services/dashboard_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/dashboard_service.py)
- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
- [backend/trading-tool-backend/backend/tests/test_platform_hardening.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_platform_hardening.py)

## Validation Snapshot

- `pytest -q backend/trading-tool-backend/backend/tests/test_platform_hardening.py` -> expected green after this tranche
- `python3 -m py_compile backend/trading-tool-backend/backend/services/dashboard_service.py backend/trading-tool-backend/backend/services/ai_assistant_service.py` -> green

## Acceptance Read

This tranche is ready when:

- no known dashboard/assistant read path concurrently awaits one shared
  `AsyncSession`
- regression tests fail if `asyncio.gather()` is reintroduced on those paths
- deploy hardening tests reflect the current wrapper-plus-shared-script layout
