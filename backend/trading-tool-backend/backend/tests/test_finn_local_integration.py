from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_local_harness_reuses_production_entrypoints_and_finn_queue():
    source = (ROOT / "ops" / "local-finn" / "finn-local.sh").read_text()
    production = (ROOT / "ops" / "deploy" / "ecosystem.shared.js").read_text()
    assert "backend.main:app" in source
    assert "backend.celery_task.celery_app" in source
    assert "local-finn-finn_interactive" in source
    assert "finn_interactive" in production
    assert "-Ofair" in source and "-Ofair" in production
    assert "FINN_LOCAL_SAFE_ADAPTERS=1" in (ROOT / "ops" / "local-finn" / "finn-local.env.example").read_text()


def test_local_compose_isolated_to_loopback_postgres_and_redis():
    compose = (ROOT / "docker-compose.finn-local.yml").read_text()
    assert "127.0.0.1:55432:5432" in compose
    assert "127.0.0.1:56379:6379" in compose
    assert "postgres:16-alpine" in compose and "redis:7-alpine" in compose
