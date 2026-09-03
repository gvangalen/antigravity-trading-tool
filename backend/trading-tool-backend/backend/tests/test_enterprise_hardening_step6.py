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
    wrapper_source = (REPO_ROOT / "deploy_live.sh").read_text()
    source = (REPO_ROOT / "ops" / "deploy" / "deploy_env.sh").read_text()

    assert "deploy_env.sh" in wrapper_source
    assert 'production main' in wrapper_source
    assert "EXPECTED_PM2_APPS=" in source
    assert "check_pm2_apps_online" in source
    assert "for attempt in" in source
    assert "tradamind_pm2_jlist.json" in source
    assert "raw.splitlines()" in source
    assert "jlist JSON payload not found" in source
    assert "PM2 gate failed" in source
    assert 'pm2 startOrReload $PM2_CONFIG --update-env && check_pm2_apps_online' in source
    assert 'for_each_pm2_app \\"$CORE_PM2_APPS\\" pm2_delete_app' in source
    assert 'pm2_start_app()' in source
    assert 'pm2 start $PM2_CONFIG --only \\"\\$app\\" --update-env' in source
    assert 'wait_for_backend_listen()' in source
    assert 'restart_backend_app()' in source
    assert 'stabilize_backend_app()' in source
    assert 'pm2 delete \\"\\$app\\" || true' in source
    assert "pm2 save --force" in source
    assert 'PM2_CONFIG="ecosystem.production.config.js"' in source


def test_deploy_script_atomically_records_the_validated_canonical_last_good_commit():
    wrapper_source = (REPO_ROOT / "deploy_live.sh").read_text()
    source = (REPO_ROOT / "ops" / "deploy" / "deploy_env.sh").read_text()
    acceptance_source = (REPO_ROOT / "ops" / "deploy" / "record_accepted_release.sh").read_text()

    assert "deploy_env.sh" in wrapper_source
    assert "REMOTE_LAST_GOOD" in source
    assert "sudo cat ${CANONICAL_DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT" in source
    assert "ROLLBACK_COMMIT" in source
    assert "ROLLBACK_COMMAND" in source
    assert "./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" in source
    assert "ops/deploy/PREVIOUS_GOOD_COMMIT" in source
    assert "RELEASE_MARKER_REASON=deployed DEPLOYMENT_VALIDATED_RELEASE=true" in source
    assert "record_accepted_release.sh" in source
    assert "LAST_GOOD_COMMIT" in acceptance_source
    assert "mktemp" in acceptance_source
    assert 'chmod 644 "$temporary"' in acceptance_source
    assert "RELEASE_MARKER_REASON" in acceptance_source
    assert "DEPLOYMENT_VALIDATED_RELEASE" in acceptance_source
    assert "CHECKOUT_MARKER" in acceptance_source
    assert 'ln -s "$CANONICAL_DEPLOY_STATE_DIR/LAST_GOOD_COMMIT"' in acceptance_source
    assert 'mv -f "$CHECKOUT_MARKER_TEMP" "$CHECKOUT_MARKER"' in acceptance_source
    assert "deployment failed for" in source
    assert "Rollback command:" in source
    assert "Canonical LAST_GOOD_COMMIT is missing" in source


def test_rollback_helper_resets_code_and_runs_health_smoke_without_migrations():
    rollback_path = REPO_ROOT / "rollback_live.sh"
    wrapper_source = rollback_path.read_text()
    source = (REPO_ROOT / "ops" / "deploy" / "rollback_env.sh").read_text()

    assert rollback_path.exists()
    assert "rollback_env.sh" in wrapper_source
    assert "ROLLBACK_COMMIT" in wrapper_source
    assert "CANONICAL_DEPLOY_STATE_DIR}/LAST_GOOD_COMMIT" in source
    assert 'tee "$CANONICAL_DEPLOY_STATE_DIR/LAST_GOOD_COMMIT"' not in source
    assert 'git reset --hard "$ROLLBACK_COMMIT"' in source
    assert 'pm2 startOrReload "$PM2_CONFIG" --update-env' in source
    assert "check_pm2_apps_online" in source
    assert "stabilize_backend_app" in source
    assert "/api/health" in source
    assert "/api/system/health" in source
    assert 'http://127.0.0.1:${FRONTEND_PORT}/report' in source
    assert "run_sql_migration.py" not in source


def test_legacy_deploy_script_is_explicitly_blocked():
    source = (REPO_ROOT / "deploy.sh").read_text()

    assert "deprecated and intentionally blocked" in source
    assert "./deploy_live.sh" in source
    assert "./deploy_staging.sh" in source
    assert "./ops/deploy/deploy_env.sh" in source
