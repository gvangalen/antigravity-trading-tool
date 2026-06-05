from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_manual_order_idempotency_is_enforced_in_schema_and_repository():
    migration = _read(
        BACKEND_ROOT
        / "scripts"
        / "migrations"
        / "2026_05_18_manual_order_idempotency.py"
    )
    repository = _read(
        BACKEND_ROOT / "infrastructure" / "repositories" / "bot_repository.py"
    )

    assert "ux_bot_orders_user_idempotency_key" in migration
    assert "ON bot_orders (user_id, idempotency_key)" in migration
    assert "WHERE idempotency_key IS NOT NULL" in migration
    assert "ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING" in repository
    assert "get_manual_order_by_idempotency_key" in repository


def test_bot_generated_execution_idempotency_is_enforced_in_schema_and_repository():
    migration = _read(
        BACKEND_ROOT
        / "scripts"
        / "migrations"
        / "2026_06_05_bot_execution_idempotency.py"
    )
    repository = _read(
        BACKEND_ROOT / "infrastructure" / "repositories" / "bot_repository.py"
    )
    agent = _read(BACKEND_ROOT / "ai_agents" / "trading_bot_agent.py")

    assert "ux_bot_executions_user_order" in migration
    assert "ON bot_executions (user_id, bot_order_id)" in migration
    assert "ux_bot_ledger_execute_user_order" in migration
    assert "ON bot_ledger (user_id, order_id, entry_type)" in migration
    assert "WHERE entry_type = 'execute' AND order_id IS NOT NULL" in migration

    assert "ON CONFLICT (user_id, bot_order_id) DO UPDATE SET" in repository
    assert "ON CONFLICT (user_id, order_id, entry_type) WHERE entry_type = 'execute' AND order_id IS NOT NULL DO NOTHING" in repository
    assert "if ledger_result.fetchone() is None:" in repository

    assert "ON CONFLICT (user_id, order_id, entry_type)" in agent
    assert "DO NOTHING" in agent
    assert "return False" in agent


def test_bot_portfolio_state_is_scoped_by_symbol_in_schema_and_runtime_paths():
    migration = _read(
        BACKEND_ROOT
        / "scripts"
        / "migrations"
        / "2026_06_05_bot_portfolio_symbol_scope.py"
    )
    repository = _read(
        BACKEND_ROOT / "infrastructure" / "repositories" / "bot_repository.py"
    )
    agent = _read(BACKEND_ROOT / "ai_agents" / "trading_bot_agent.py")

    assert "ux_bot_portfolios_bot_symbol" in migration
    assert "ON bot_portfolios (bot_id, symbol)" in migration
    assert "DROP INDEX IF EXISTS" in migration

    assert "ON CONFLICT (bot_id, symbol) DO UPDATE SET" in repository
    assert "p.symbol = COALESCE(NULLIF(UPPER(c.symbol), ''), NULLIF(UPPER(st.symbol), ''), 'BTC')" in repository

    assert "ON CONFLICT (bot_id, symbol) DO UPDATE SET" in agent
    assert "WHERE user_id = %s AND bot_id = %s AND symbol = %s" in agent
    assert 'portfolio_state = get_bot_portfolio_state(conn, user_id, bot["bot_id"], symbol)' in agent


def test_bot_decision_generation_is_unique_per_user_bot_decision_date():
    source = _read(BACKEND_ROOT / "ai_agents" / "trading_bot_agent.py")

    assert "ON CONFLICT (user_id, bot_id, decision_date) DO UPDATE SET" in source
    assert "RETURNING id" in source


def test_live_manual_order_preflight_is_required_before_persistence():
    source = _read(BACKEND_ROOT / "services" / "bot_service.py")

    create_method_index = source.index("async def create_manual_order")
    preflight_context_index = source.index(
        "require_live_manual_order_preflight_context", create_method_index
    )
    insert_index = source.index("repository.create_manual_order", create_method_index)

    assert preflight_context_index < insert_index
    assert "LIVE_ORDER_IDEMPOTENCY_REQUIRED" in source
    assert "LIVE_ORDER_RISK_ACK_REQUIRED" in source
    assert "LIVE_PREFLIGHT_REQUIRED" in source


def test_bot_execution_paths_use_atomic_claim_and_failed_execution_boundary():
    source = _read(BACKEND_ROOT / "ai_agents" / "trading_bot_agent.py")
    task_source = _read(BACKEND_ROOT / "celery_task" / "trading_bot_task.py")

    assert "SET status='executing'" in source
    assert "AND status='planned'" in source
    assert "RETURNING id" in source
    assert "SET status='failed_execution'" in source
    assert "Decision already processing or executed" in source
    assert "raise RuntimeError(result.get(\"error\") or \"trading_bot_agent_failed\")" in task_source
