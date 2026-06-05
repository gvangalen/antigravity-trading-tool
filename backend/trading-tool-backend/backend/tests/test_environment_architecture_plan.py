from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_environment_architecture_doc_tracks_staging_and_production_split():
    source = _read(REPO_ROOT / "docs" / "operations" / "environment-architecture.md")

    assert "staging.tradamind.com" in source
    assert "api-staging.tradamind.com" in source
    assert "app.tradamind.com" in source
    assert "api.tradamind.com" in source
    assert "`develop` for staging deploys" in source
    assert "`main` for production deploys" in source


def test_shared_deploy_scripts_support_multiple_environments():
    deploy_source = _read(REPO_ROOT / "ops" / "deploy" / "deploy_env.sh")
    rollback_source = _read(REPO_ROOT / "ops" / "deploy" / "rollback_env.sh")

    assert 'production)' in deploy_source
    assert 'staging)' in deploy_source
    assert "ecosystem.production.config.js" in deploy_source
    assert "ecosystem.staging.config.js" in deploy_source
    assert "ops/deploy/${ENVIRONMENT}" in deploy_source
    assert 'production)' in rollback_source
    assert 'staging)' in rollback_source


def test_terraform_stack_models_both_staging_and_production():
    source = _read(
        REPO_ROOT
        / "backend"
        / "trading-tool-backend"
        / "backend"
        / "infrastructure"
        / "oci"
        / "main.tf"
    )

    assert "production =" in source
    assert "staging =" in source
    assert 'display_name     = "tradamind-production"' in source
    assert 'display_name     = "tradamind-staging"' in source
    assert "resource \"oci_core_instance\" \"environment_vm\"" in source
