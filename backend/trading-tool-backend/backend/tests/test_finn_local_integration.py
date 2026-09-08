from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_local_harness_reuses_production_entrypoints_and_finn_queue():
    source = (ROOT / "ops" / "local-finn" / "finn-local.sh").read_text()
    production = (ROOT / "ops" / "deploy" / "ecosystem.shared.js").read_text()
    assert "backend.main:app" in source
    assert "backend.celery_task.celery_app" in source
    assert "local-finn-finn_interactive" in source
    assert "--pool=solo" in source
    assert "finn_interactive" in production
    assert "-Ofair" in source and "-Ofair" in production
    assert "FINN_LOCAL_SAFE_ADAPTERS=1" in (ROOT / "ops" / "local-finn" / "finn-local.env.example").read_text()


def test_local_compose_isolated_to_loopback_postgres_and_redis():
    compose = (ROOT / "docker-compose.finn-local.yml").read_text()
    assert "127.0.0.1:55432:5432" in compose
    assert "127.0.0.1:56379:6379" in compose
    assert "postgres:16" in compose and "redis:alpine" in compose


def test_local_harness_bootstraps_legacy_schema_before_canonical_migrations():
    source = (ROOT / "ops" / "local-finn" / "finn-local.sh").read_text()
    bootstrap = (ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "bootstrap_local_finn_schema.py").read_text()
    assert source.index("bootstrap_local_finn_schema.py") < source.index("run_sql_migration.py")
    assert "Base.metadata.create_all" in bootstrap
    assert "bot_orders" in bootstrap and "bot_configs" in bootstrap
    assert "content_hash" in bootstrap and "payload_json" in bootstrap


def test_local_safe_adapters_require_the_exact_local_application_environment(monkeypatch):
    from backend.services.finn_v2_flag_service import FinnV2FlagService

    monkeypatch.setenv("FINN_LOCAL_SAFE_ADAPTERS", "1")
    monkeypatch.setenv("APP_ENV", "production")
    assert FinnV2FlagService().is_local_safe_action_adapters_enabled() is False

    monkeypatch.setenv("APP_ENV", "local_finn")
    flags = FinnV2FlagService()
    assert flags.is_local_safe_action_adapters_enabled() is True
    assert flags.execute_setup_changes_enabled() is True
    assert flags.execute_bot_changes_enabled() is True
    assert flags.execute_live_bot_activation_enabled() is False
