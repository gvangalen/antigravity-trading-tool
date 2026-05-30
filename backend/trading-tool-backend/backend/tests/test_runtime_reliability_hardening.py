from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def test_intelligence_event_service_degrades_missing_mobile_push_table_to_warning():
    source = (BACKEND_ROOT / "services" / "intelligence_event_service.py").read_text(encoding="utf-8")

    assert "def _is_missing_mobile_push_table" in source
    assert "mobile_push_tokens" in source
    assert "does not exist" in source
    assert "undefinedtable" in source
    assert "no such table" in source
    assert 'logger.warning("Push notification dispatch overgeslagen: mobile_push_tokens table ontbreekt nog.")' in source


def test_deploy_env_supports_backend_only_auto_rollback_and_previous_markers():
    source = (REPO_ROOT / "ops" / "deploy" / "deploy_env.sh").read_text(encoding="utf-8")

    assert 'DEPLOY_COMPONENT_SET="${DEPLOY_COMPONENT_SET:-full}"' in source
    assert 'AUTO_ROLLBACK_ON_FAILURE="${AUTO_ROLLBACK_ON_FAILURE:-true}"' in source
    assert 'if [ "$DEPLOY_COMPONENT_SET" = "backend_only" ]; then' in source
    assert 'if [ "${AUTO_ROLLBACK_ON_FAILURE,,}" = "true" ]; then' in source
    assert "./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" in source
    assert "External smoke failed" in source
    assert "PREVIOUS_GOOD_COMMIT" in source
    assert "/var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT" in source


def test_rollback_env_persists_previous_commit_and_pm2_fallback():
    source = (REPO_ROOT / "ops" / "deploy" / "rollback_env.sh").read_text(encoding="utf-8")

    assert 'CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"' in source
    assert "PM2 config $PM2_CONFIG not found; falling back to ecosystem.config.js." in source
    assert 'printf "%s\\n" "$CURRENT_COMMIT" > "${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT"' in source
    assert 'sudo tee /var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT' in source
