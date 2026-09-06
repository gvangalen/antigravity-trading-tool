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
    assert 'MIGRATION_COMMAND_TIMEOUT_SECONDS="${MIGRATION_COMMAND_TIMEOUT_SECONDS:-180}"' in source
    assert 'REMOTE_DEPLOY_COMMAND_TIMEOUT_SECONDS="${REMOTE_DEPLOY_COMMAND_TIMEOUT_SECONDS:-900}"' in source
    assert 'DEEP_HEALTH_ATTEMPTS="${DEEP_HEALTH_ATTEMPTS:-30}"' in source
    assert 'DEEP_HEALTH_RETRY_DELAY_SECONDS="${DEEP_HEALTH_RETRY_DELAY_SECONDS:-10}"' in source
    assert 'STRICT_DEEP_HEALTH="${STRICT_DEEP_HEALTH:-true}"' in source
    assert 'INTERACTIVE_WORKER_READY_ATTEMPTS="${INTERACTIVE_WORKER_READY_ATTEMPTS:-45}"' in source
    assert 'BACKEND_INITIAL_LISTEN_ATTEMPTS="${BACKEND_INITIAL_LISTEN_ATTEMPTS:-180}"' in source
    assert 'BACKEND_INITIAL_HEALTH_ATTEMPTS="${BACKEND_INITIAL_HEALTH_ATTEMPTS:-90}"' in source
    assert 'BACKEND_RECOVERY_LISTEN_ATTEMPTS="${BACKEND_RECOVERY_LISTEN_ATTEMPTS:-180}"' in source
    assert 'BACKEND_RECOVERY_HEALTH_ATTEMPTS="${BACKEND_RECOVERY_HEALTH_ATTEMPTS:-90}"' in source
    assert 'STRICT_EXTERNAL_SMOKE="${STRICT_EXTERNAL_SMOKE:-false}"' in source
    assert "lower_bool()" in source
    assert 'if [ "$DEPLOY_COMPONENT_SET" = "backend_only" ]; then' in source
    assert 'if [ "$(lower_bool "${AUTO_ROLLBACK_ON_FAILURE}")" = "true" ]; then' in source
    assert "./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" in source
    assert "external_smoke_failed=false" in source
    assert source.count("curl --connect-timeout 5 --max-time 20") == 2
    assert 'timeout --foreground "${REMOTE_DEPLOY_COMMAND_TIMEOUT_SECONDS}s" ssh' in source
    assert 'if [ "$(lower_bool "${STRICT_EXTERNAL_SMOKE}")" = "true" ]; then' in source
    assert "External smoke failed" in source
    assert "rollout continues because STRICT_EXTERNAL_SMOKE=false" in source
    assert "PREVIOUS_GOOD_COMMIT" in source
    assert "/var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT" in source
    assert 'BACKEND_APP="${BACKEND_APP:-backend}"' in source
    assert 'wait_for_backend_listen()' in source
    assert 'restart_backend_app()' in source
    assert 'wait_for_backend_health "$BACKEND_INITIAL_HEALTH_ATTEMPTS"' in source
    assert 'wait_for_backend_health "$BACKEND_RECOVERY_HEALTH_ATTEMPTS"' in source
    assert "--noproxy '*' --connect-timeout 2 --max-time 5" in source
    assert "TRADAMIND_BUILD_COMMIT_SHA" in source
    assert "actual == expected" in source
    assert 'deep_health_ready=false' in source
    assert 'for attempt in \\$(seq 1 \\"$DEEP_HEALTH_ATTEMPTS\\"); do' in source
    assert 'Deep health not ready yet' in source
    assert 'bash ./ops/deploy/bootstrap_runtime_dependencies.sh' in source
    assert 'timeout --foreground \\"\\${MIGRATION_COMMAND_TIMEOUT_SECONDS}s\\"' in source
    assert "2026_08_20_finn_v2_canonical_modes.py" in source
    assert source.index("2026_08_18_finn_v2_typed_operation_modes.py") < source.index("2026_08_20_finn_v2_canonical_modes.py")
    assert "2026_08_23_finn_v2_conversation_context.py" in source
    assert "2026_08_23_finn_v2_evidence_information_scope.py" in source
    assert "2026_08_23_finn_v2_artifact_operation_contract.py" in source
    assert "python3 -m backend.scripts.check_finn_v2_schema" in source
    assert source.index("2026_08_22_finn_v2_remove_legacy_fact_mode.py") < source.index("2026_08_23_finn_v2_conversation_context.py")
    assert source.index("2026_08_23_finn_v2_conversation_context.py") < source.index("python3 -m backend.scripts.check_finn_v2_schema")
    assert source.index("2026_08_23_finn_v2_conversation_context.py") < source.index("2026_08_23_finn_v2_evidence_information_scope.py")
    assert source.index("2026_08_23_finn_v2_evidence_information_scope.py") < source.index("python3 -m backend.scripts.check_finn_v2_schema")
    assert source.index("2026_08_23_finn_v2_artifact_operation_contract.py") < source.index("python3 -m backend.scripts.check_finn_v2_schema")
    assert source.index("2026_08_25_finn_v2_indicator_config_reconciliation.py") < source.index("python3 -m backend.scripts.check_finn_v2_schema")
    assert source.index("python3 -m backend.scripts.check_finn_v2_schema") < source.index("pm2_start_app()")
    assert "wait_for_interactive_worker_ready()" in source
    assert "/api/system/health" in source
    assert "queues.get('finn_interactive')" in source
    assert source.index("start_interactive_worker_first") < source.index("start_remaining_auxiliary_apps")


def test_auto_deploy_serializes_production_and_retries_once_after_a_failed_attempt():
    source = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "group: auto-deploy-production" in source
    assert "cancel-in-progress: false" in source
    assert 'for attempt in 1 2; do' in source
    assert 'sleep 30' in source


def test_sql_migration_runner_bounds_lock_and_statement_waits():
    source = (BACKEND_ROOT / "scripts" / "run_sql_migration.py").read_text(encoding="utf-8")

    assert 'TRADAMIND_MIGRATION_LOCK_TIMEOUT_MS' in source
    assert 'TRADAMIND_MIGRATION_STATEMENT_TIMEOUT_MS' in source
    assert 'SET LOCAL lock_timeout = %s' in source
    assert 'SET LOCAL statement_timeout = %s' in source


def test_rollback_env_persists_previous_commit_and_pm2_fallback():
    source = (REPO_ROOT / "ops" / "deploy" / "rollback_env.sh").read_text(encoding="utf-8")

    assert 'CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"' in source
    assert 'echo "❌ PM2 config $PM2_CONFIG not found on remote host." >&2' in source
    assert "Waiting for git lock to clear during rollback" in source
    assert 'printf "%s\\n" "$CURRENT_COMMIT" > "${DEPLOY_STATE_DIR}/PREVIOUS_GOOD_COMMIT"' in source
    assert 'sudo tee /var/www/tradamind/ops/deploy/PREVIOUS_GOOD_COMMIT' in source
    assert 'stabilize_backend_app' in source


def test_runtime_bootstrap_covers_backend_frontend_and_playwright_dependencies():
    source = (REPO_ROOT / "ops" / "deploy" / "bootstrap_runtime_dependencies.sh").read_text(encoding="utf-8")
    requirements = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert 'python3 -m pip install -r "${BACKEND_REQUIREMENTS}"' in source
    assert 'npm ci --no-audit --no-fund' in source
    assert 'python3 -m playwright install chromium' in source
    assert 'required = ("email_validator", "playwright", "faiss")' in source
    assert "email-validator" in requirements
    assert "playwright" in requirements
    assert "faiss-cpu" in requirements


def test_deploy_env_applies_mobile_push_token_migration():
    source = (REPO_ROOT / "ops" / "deploy" / "deploy_env.sh").read_text(encoding="utf-8")
    migration = (BACKEND_ROOT / "scripts" / "migrations" / "2026_06_24_mobile_push_tokens.py").read_text(encoding="utf-8")

    assert "2026_06_24_mobile_push_tokens.py" in source
    assert "CREATE TABLE IF NOT EXISTS mobile_push_tokens" in migration
    assert "push_token VARCHAR NOT NULL UNIQUE" in migration


def test_deploy_env_applies_asset_catalog_and_indicator_scope_migrations():
    source = (REPO_ROOT / "ops" / "deploy" / "deploy_env.sh").read_text(encoding="utf-8")

    assert "2026_08_05_asset_catalog_provider_routing.py" in source
    assert "2026_08_06_user_indicator_symbol_overrides.py" in source
    assert source.index("2026_08_05_asset_catalog.py") < source.index("2026_08_05_asset_catalog_provider_routing.py")
    assert source.index("2026_08_05_asset_catalog_provider_routing.py") < source.index("2026_08_06_user_indicator_symbol_overrides.py")


def test_deploy_env_applies_the_finn_v2_canonical_mode_backfill():
    source = (REPO_ROOT / "ops" / "deploy" / "deploy_env.sh").read_text(encoding="utf-8")

    assert "2026_08_22_finn_v2_remove_legacy_fact_mode.py" in source


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
