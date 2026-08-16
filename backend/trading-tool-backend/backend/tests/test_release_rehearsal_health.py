from pathlib import Path


def test_health_route_reports_app_env():
    source = Path("backend/trading-tool-backend/backend/main.py").read_text(encoding="utf-8")
    assert '"app_env": os.getenv("APP_ENV", "production")' in source
    assert '"build": build_metadata_snapshot(service="backend")' in source
