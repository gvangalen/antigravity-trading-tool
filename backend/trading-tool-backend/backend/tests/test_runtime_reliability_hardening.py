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
    assert "lower_bool()" in source
    assert 'if [ "$DEPLOY_COMPONENT_SET" = "backend_only" ]; then' in source
    assert 'if [ "$(lower_bool "${AUTO_ROLLBACK_ON_FAILURE}")" = "true" ]; then' in source
    assert "./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" in source
    assert "External smoke failed" in source
    assert "PREVIOUS_GOOD_COMMIT" in source
    assert "/var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT" in source


def test_rollback_env_persists_previous_commit_and_pm2_fallback():
    source = (REPO_ROOT / "ops" / "deploy" / "rollback_env.sh").read_text(encoding="utf-8")

    assert 'CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"' in source
    assert 'echo "❌ PM2 config $PM2_CONFIG not found on remote host." >&2' in source
    assert 'printf "%s\\n" "$CURRENT_COMMIT" > "${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT"' in source
    assert 'sudo tee /var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT' in source


def test_mission_control_api_uses_short_ttl_cache_and_invalidates_after_finn_execute():
    source = (BACKEND_ROOT / "api" / "ai_assistant_api.py").read_text(encoding="utf-8")

    assert 'MISSION_CONTROL_CACHE_TTL_SECONDS = int(os.getenv("MISSION_CONTROL_CACHE_TTL_SECONDS", "20"))' in source
    assert "_mission_control_cache" in source
    assert "def _get_cached_mission_control" in source
    assert "def _store_cached_mission_control" in source
    assert "def _invalidate_mission_control_cache" in source
    assert "cached = _get_cached_mission_control(current_user[\"id\"])" in source
    assert "_store_cached_mission_control(current_user[\"id\"], response)" in source
    assert "_invalidate_mission_control_cache(user_id)" in source


def test_portfolio_intelligence_context_batches_market_prices():
    source = (BACKEND_ROOT / "infrastructure" / "repositories" / "bot_repository.py").read_text(encoding="utf-8")

    assert "async def get_market_prices(self, symbols: List[str]) -> Dict[str, float]:" in source
    assert "SELECT DISTINCT ON (symbol) symbol, price" in source
    assert "WHERE symbol = ANY(:symbols)" in source
    assert "prices = await self.get_market_prices(symbols)" in source
