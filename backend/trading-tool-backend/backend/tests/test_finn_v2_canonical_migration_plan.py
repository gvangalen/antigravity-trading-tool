from __future__ import annotations

from pathlib import Path

import pytest

from backend.scripts.validate_finn_v2_migration_plan import assert_finn_v2_migration_plan


REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "migrations"
DEPLOY_SCRIPT = REPO_ROOT / "ops" / "deploy" / "deploy_env.sh"


def test_every_canonical_finn_v2_migration_is_in_the_deployment_plan():
    assert_finn_v2_migration_plan(migrations_dir=MIGRATIONS, deploy_script=DEPLOY_SCRIPT)


def test_missing_canonical_migration_fails_before_service_start(tmp_path):
    deploy_script = tmp_path / "deploy_env.sh"
    deploy_script.write_text("run_migration backend/scripts/migrations/2026_08_17_finn_v2_foundation.py\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="canonical_finn_v2_migrations_missing_from_deploy_plan"):
        assert_finn_v2_migration_plan(migrations_dir=MIGRATIONS, deploy_script=deploy_script)


def test_runtime_contract_migration_is_idempotent_and_non_destructive():
    source = (MIGRATIONS / "2026_09_04_finn_v2_runtime_contract_foundation.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS finn_v2_runtime_contracts" in source
    assert source.count("CREATE INDEX IF NOT EXISTS") == 3
    assert "DROP TABLE" not in source.split("ROLLBACK_SQL", 1)[0]
