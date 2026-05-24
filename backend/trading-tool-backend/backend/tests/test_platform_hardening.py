import inspect
import asyncio
from pathlib import Path

from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.ai_gateway import AiGateway
from backend.services.dashboard_service import DashboardService
from backend.services import portfolio_snapshot_service


class _ExecResult:
    def fetchone(self):
        return None


class _FakeAsyncSession:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, query, params=None):
        self.executed.append({"sql": str(query), "params": params or {}})
        return _ExecResult()

    async def commit(self):
        self.commits += 1


def test_conversation_state_save_uses_single_user_upsert():
    session = _FakeAsyncSession()
    repo = ConversationStateRepository(session)

    asyncio.run(repo.save_state(7, "bot_decision", "BTC", {"step": "ack"}))

    sql = session.executed[0]["sql"].lower()
    assert "insert into conversation_state" in sql
    assert "on conflict (user_id) do update" in sql
    assert "select id from conversation_state" not in sql
    assert session.commits == 1


def test_ai_usage_update_is_atomic_increment_sql():
    session = _FakeAsyncSession()
    repo = UserRepository(session)

    asyncio.run(repo.update_ai_usage(7, requests=2, cost=0.25, tokens=50))

    sql = session.executed[0]["sql"].lower()
    assert "update users set" in sql
    assert "coalesce" in sql
    assert "ai_requests_used_day" in sql
    assert "ai_usage_current" in sql
    assert "ai_tokens_used_month" in sql
    assert session.commits == 1


def test_ai_cache_save_uses_context_composite_conflict_key():
    session = _FakeAsyncSession()
    user_repo = type("UserRepo", (), {"db": session})()
    score_repo = object()
    gateway = AiGateway(user_repo, score_repo)

    asyncio.run(gateway._save_cache(
        query_hash="same-hash",
        text_query="same prompt",
        norm_query="same prompt",
        response={"ok": True},
        cost=0.1,
        symbol="BTC",
        timeframe="1D",
        category="assistant",
        ttl=60,
        embedding=[0.1, 0.2],
    ))

    sql = session.executed[0]["sql"].lower()
    assert "on conflict (query_hash, symbol, timeframe, category) do update" in sql
    assert session.executed[0]["params"]["s"] == "BTC"
    assert session.executed[0]["params"]["tf"] == "1D"
    assert session.executed[0]["params"]["cat"] == "assistant"


def test_mobile_overview_does_not_parallelize_shared_session_work():
    source = inspect.getsource(DashboardService.get_mobile_overview)

    assert "asyncio.gather" not in source
    assert "get_latest_prices_and_changes" in source
    assert "get_bot_portfolios" in source


def test_main_startup_is_schema_read_only():
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    source = main_path.read_text()

    assert "async def database_migrations" not in source
    assert "ALTER TABLE" not in source
    assert "CREATE TABLE" not in source
    assert "CREATE INDEX" not in source
    assert "DROP CONSTRAINT" not in source
    assert "ADD CONSTRAINT" not in source


def test_deploy_script_has_no_user_specific_business_actions():
    deploy_path = Path(__file__).resolve().parents[4] / "deploy_live.sh"
    source = deploy_path.read_text()

    assert "UID=30" not in source
    assert "run_market_agent" not in source
    assert "run_macro_agent" not in source
    assert "run_technical_agent" not in source
    assert "run_setup_agent" not in source
    assert "/api/health" in source
    assert "/api/system/health" in source
    assert "tradamind_deep_health.json" in source
    assert "json.load" in source
    assert "STRICT_DEEP_HEALTH" in source
    assert '"down", "error"' in source


class _FakeCursor:
    def __init__(self, prices, portfolios):
        self.prices = prices
        self.portfolios = portfolios
        self._rows = []
        self.inserted_bot_snapshots = []

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        params = params or ()
        if "from market_data" in sql_lower:
            symbol = params[0]
            price = self.prices.get(symbol)
            self._rows = [(price,)] if price is not None else []
            return
        if "from bot_portfolios" in sql_lower:
            self._rows = list(self.portfolios)
            return
        if "insert into bot_portfolio_snapshots" in sql_lower:
            self.inserted_bot_snapshots.append(params)
            self._rows = []
            return
        self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_portfolio_snapshot_uses_bot_symbol_price(monkeypatch):
    cursor = _FakeCursor(
        prices={"BTC": 50000, "ETH": 2500},
        portfolios=[
            # bot_id, symbol, cash, qty, invested, avg_entry, realized
            (101, "ETH", 100, 2, 4000, 2000, 0),
        ],
    )
    monkeypatch.setattr(portfolio_snapshot_service, "get_db_connection", lambda: _FakeConnection(cursor))

    portfolio_snapshot_service.snapshot_all_for_user(9)

    assert cursor.inserted_bot_snapshots
    params = cursor.inserted_bot_snapshots[0]
    assert params[4] == "ETH"
    assert params[7] == 2500
    assert params[8] == 5100


def test_portfolio_snapshot_skips_bot_when_symbol_price_missing(monkeypatch):
    cursor = _FakeCursor(
        prices={"BTC": 50000},
        portfolios=[
            (101, "ETH", 100, 2, 4000, 2000, 0),
        ],
    )
    monkeypatch.setattr(portfolio_snapshot_service, "get_db_connection", lambda: _FakeConnection(cursor))

    portfolio_snapshot_service.snapshot_all_for_user(9)

    assert cursor.inserted_bot_snapshots == []
