from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_api_adds_request_trace_id_middleware():
    source = (REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "main.py").read_text()

    assert '@app.middleware("http")' in source
    assert "request_trace_id_middleware" in source
    assert "x-trace-id" in source
    assert 'response.headers["X-Trace-Id"]' in source
    assert "request.state.trace_id" in source


def test_deploy_script_gates_pm2_processes_and_has_fallback_rebuild():
    source = (REPO_ROOT / "deploy_live.sh").read_text()

    assert "expected_pm2_apps=" in source
    assert "check_pm2_apps_online" in source
    assert "for attempt in" in source
    assert "tradamind_pm2_jlist.json" in source
    assert "raw.splitlines()" in source
    assert "jlist JSON payload not found" in source
    assert "PM2 gate failed" in source
    assert "pm2 startOrReload ecosystem.config.js --update-env && check_pm2_apps_online" in source
    assert "pm2 delete all || true" in source
    assert "pm2 start ecosystem.config.js --update-env" in source
    assert "pm2 save --force" in source
