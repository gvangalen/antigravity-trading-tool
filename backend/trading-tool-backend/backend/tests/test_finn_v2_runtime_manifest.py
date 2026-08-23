"""Prevent a partial main branch from silently dropping FINN V2 runtime blocks."""

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_RUNTIME_FILES = (
    "api/finn_v2_api.py",
    "celery_task/finn_v2_task.py",
    "domain/finn_v2_contract.py",
    "services/finn_v2_gateway_service.py",
    "services/finn_v2_run_service.py",
    "services/finn_v2_tool_execution_service.py",
    "services/finn_v2_state_assembly_service.py",
    "services/finn_v2_orchestrator_service.py",
    "services/finn_v2_policy_engine_service.py",
    "services/finn_v2_reasoning_service.py",
    "services/finn_v2_response_verifier_service.py",
    "services/finn_v2_visible_delivery_service.py",
    "services/finn_v2_proposal_service.py",
    "services/finn_v2_confirmation_service.py",
    "services/finn_v2_execution_service.py",
)

REQUIRED_MIGRATIONS = (
    "2026_08_17_finn_v2_foundation.py",
    "2026_08_17_finn_v2_tool_registry.py",
    "2026_08_17_finn_v2_evidence_state.py",
    "2026_08_17_finn_v2_orchestrator.py",
    "2026_08_17_finn_v2_policy_confirmation.py",
    "2026_08_17_finn_v2_reasoning.py",
    "2026_08_17_finn_v2_verified_delivery.py",
    "2026_08_17_finn_v2_evals_cutover_execution.py",
    "2026_08_22_finn_v2_run_lifecycle_statuses.py",
    "2026_08_22_finn_v2_remove_legacy_fact_mode.py",
    "2026_08_23_finn_v2_evidence_information_scope.py",
)


def test_finn_v2_runtime_and_migration_manifest_is_complete():
    missing_runtime = [path for path in REQUIRED_RUNTIME_FILES if not (BACKEND_ROOT / path).is_file()]
    migration_root = BACKEND_ROOT / "scripts" / "migrations"
    missing_migrations = [name for name in REQUIRED_MIGRATIONS if not (migration_root / name).is_file()]

    assert not missing_runtime, f"missing FINN V2 runtime files: {missing_runtime}"
    assert not missing_migrations, f"missing FINN V2 migrations: {missing_migrations}"
