"""Reject a deploy plan that omits a checked-in FINN V2 migration."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


MIGRATION_CALL = re.compile(r"^\s*run_migration\s+backend/scripts/migrations/([^\s]+)", re.MULTILINE)


def canonical_finn_v2_migrations(migrations_dir: Path) -> set[str]:
    """FINN V2 migration names are the canonical, deploy-required family."""
    return {
        path.name
        for path in migrations_dir.glob("*_finn_v2_*.py")
        if path.is_file() and not path.name.startswith("__")
    }


def registered_migrations(deploy_script: Path) -> set[str]:
    return set(MIGRATION_CALL.findall(deploy_script.read_text(encoding="utf-8")))


def assert_finn_v2_migration_plan(*, migrations_dir: Path, deploy_script: Path) -> None:
    missing = sorted(canonical_finn_v2_migrations(migrations_dir) - registered_migrations(deploy_script))
    if missing:
        raise RuntimeError("canonical_finn_v2_migrations_missing_from_deploy_plan:" + ",".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the canonical FINN V2 deployment migration plan.")
    parser.add_argument("--deploy-script", type=Path, required=True)
    parser.add_argument("--migrations-dir", type=Path, default=Path(__file__).resolve().parent / "migrations")
    args = parser.parse_args()
    assert_finn_v2_migration_plan(
        migrations_dir=args.migrations_dir.resolve(),
        deploy_script=args.deploy_script.resolve(),
    )
    print("FINN V2 canonical migration plan validated")


if __name__ == "__main__":
    main()
