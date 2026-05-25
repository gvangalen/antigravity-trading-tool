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
