from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "scripts" / "migrations" / "2026_08_18_finn_v2_typed_operation_modes.py"
CAPABILITY_MIGRATION = ROOT / "scripts" / "migrations" / "2026_08_18_finn_v2_capability_mode.py"


def test_typed_operation_mode_migration_accepts_legacy_and_current_contract_values():
    source = MIGRATION.read_text(encoding="utf-8")

    for value in (
        "FACT",
        "CAPABILITY",
        "EVALUATION",
        "PROPOSAL",
        "ACTION",
        "READ",
        "EVALUATE",
        "CREATE_PROPOSAL",
        "ACTION_PROPOSAL",
        "CLARIFICATION",
        "CONFIRMATION",
        "EXECUTION",
        "UNAVAILABLE",
    ):
        assert f"'{value}'" in source

    assert "ck_finn_v2_runs_interaction_mode" in source
    assert "ck_finn_v2_orchestrator_mode" in source
    assert "ck_finn_v2_reasoning_mode" in source
    assert "ck_finn_v2_verified_mode" in source


def test_typed_operation_mode_migration_exposes_rollback_to_capability_baseline():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ROLLBACK_SQL" in source
    assert source.count("DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode") == 2
    assert source.count("DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode") == 2
    assert source.count("DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode") == 2


def test_capability_mode_migration_is_forward_compatible_with_typed_modes():
    source = CAPABILITY_MIGRATION.read_text(encoding="utf-8")

    for value in (
        "FACT",
        "CAPABILITY",
        "EVALUATION",
        "PROPOSAL",
        "ACTION",
        "READ",
        "EVALUATE",
        "CREATE_PROPOSAL",
        "ACTION_PROPOSAL",
        "CLARIFICATION",
        "CONFIRMATION",
        "EXECUTION",
        "UNAVAILABLE",
    ):
        assert f"'{value}'" in source
