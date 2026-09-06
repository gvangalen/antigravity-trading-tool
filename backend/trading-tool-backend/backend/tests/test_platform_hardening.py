import inspect
import asyncio
from pathlib import Path
from types import SimpleNamespace

from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.dashboard_repository import DashboardRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.ai_gateway import AiGateway
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.dashboard_service import DashboardService
from backend.services import portfolio_snapshot_service


class _ExecResult:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeAsyncSession:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, query, params=None):
        self.executed.append({"sql": str(query), "params": params or {}})
        return _ExecResult()

    async def commit(self):
        self.commits += 1


class _FakeColumnResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeIsolatedUsageSession:
    def __init__(self, supported_columns):
        self.supported_columns = supported_columns
        self.executed = []
        self.commits = 0

    async def execute(self, query, params=None):
        sql = str(query)
        self.executed.append({"sql": sql, "params": params or {}})
        if "information_schema.columns" in sql:
            return _FakeColumnResult([(column,) for column in self.supported_columns])
        return _ExecResult()

    async def commit(self):
        self.commits += 1


class _FakeAsyncSessionFactory:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_dashboard_top_setups_uses_current_strategy_storage_shape():
    session = _FakeAsyncSession()
    repo = DashboardRepository(session)

    asyncio.run(repo.get_top_setups(7, limit=5))

    sql = session.executed[0]["sql"].lower()
    assert "from strategies s" in sql
    assert "left join setups st on st.id = s.setup_id" in sql
    assert "s.created_at as timestamp" in sql
    assert "coalesce(nullif(s.data->>'score', '')::float, 0) as score" in sql
    assert "select name, score, timeframe, symbol, explanation, timestamp" not in sql
    assert session.executed[0]["params"] == {"user_id": 7, "limit": 5}


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


def test_ai_preferences_update_reassigns_jsonb_payload_for_persistence():
    class _FakeAsyncSessionWithRefresh:
        def __init__(self):
            self.commits = 0
            self.refreshes = 0

        async def commit(self):
            self.commits += 1

        async def refresh(self, user):
            self.refreshes += 1

    session = _FakeAsyncSessionWithRefresh()
    repo = UserRepository(session)
    original_prefs = {
        "tone": "balanced",
        "trader_types": ["investor"],
    }
    user = SimpleNamespace(ai_preferences=original_prefs)

    async def _get_by_id(_user_id):
        return user

    repo.get_by_id = _get_by_id

    updated = asyncio.run(repo.update_ai_preferences(7, {
        "trader_types": ["swing_trader"],
        "behavior_flags": ["fomo"],
    }))

    assert updated is user
    assert session.commits == 1
    assert session.refreshes == 1
    assert user.ai_preferences["trader_types"] == ["swing_trader"]
    assert user.ai_preferences["behavior_flags"] == ["fomo"]
    assert user.ai_preferences is not original_prefs
    assert original_prefs == {
        "tone": "balanced",
        "trader_types": ["investor"],
    }


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


def test_ai_usage_logging_uses_isolated_compat_session(monkeypatch):
    class _MainSession:
        async def execute(self, query, params=None):
            raise AssertionError("shared request session should not be used for ai usage logging")

    main_session = _MainSession()
    isolated_session = _FakeIsolatedUsageSession(
        supported_columns={
            "user_id",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "cost",
            "purpose",
            "status",
            "response_time_ms",
            "estimated_cost_if_full",
            "similarity_score",
            "cache_age_seconds",
            "rejected_reason",
            "symbol",
        }
    )

    monkeypatch.setattr("backend.services.ai_gateway.async_session_factory", lambda: _FakeAsyncSessionFactory(isolated_session))

    user_repo = type("UserRepo", (), {"db": main_session})()
    gateway = AiGateway(user_repo, object())

    asyncio.run(
        gateway._log_usage(
            user_id=7,
            model="gpt-4o-mini",
            p_tokens=10,
            c_tokens=5,
            cost=0.02,
            purpose="assistant",
            status="full_ai",
            response_time_ms=123,
            estimated_cost_if_full=0.02,
            request_source="staging_user",
            app_env="staging",
            run_kind="interactive",
            entry_point="ai_gateway:assistant",
            user_email_snapshot="qa@example.com",
        )
    )

    insert_sql = isolated_session.executed[-1]["sql"].lower()
    assert "insert into ai_usage_logs" in insert_sql
    assert "request_source" not in insert_sql
    assert isolated_session.commits == 1


def test_mobile_overview_does_not_parallelize_shared_session_work():
    source = inspect.getsource(DashboardService.get_mobile_overview)

    assert "asyncio.gather" not in source
    assert "get_latest_prices_and_changes" in source
    assert "get_bot_portfolios" in source


def test_dashboard_data_does_not_parallelize_shared_session_work():
    source = inspect.getsource(DashboardService.get_dashboard_data)

    assert "asyncio.gather" not in source
    assert "get_latest_market_data" in source
    assert "get_latest_technical_data" in source


def test_assistant_context_builder_does_not_parallelize_shared_session_work():
    source = inspect.getsource(AiAssistantService._build_context)

    assert "asyncio.gather" not in source
    assert "get_master_score" in source
    assert "get_user_setups" in source
    assert "get_last_strategy" in source
    assert "get_bot_history" in source


def test_main_startup_is_schema_read_only():
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    source = main_path.read_text()

    assert "async def database_migrations" not in source
    assert "ALTER TABLE" not in source
    assert "CREATE TABLE" not in source
    assert "CREATE INDEX" not in source
    assert "DROP CONSTRAINT" not in source
    assert "ADD CONSTRAINT" not in source


def test_main_warms_finn_broker_outside_the_visible_request_path():
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    source = main_path.read_text()

    assert "async def warm_finn_dispatch_broker" in source
    assert "connection_for_write()" in source
    assert "FINN dispatch broker warmed before serving requests" in source


def test_deploy_script_has_no_user_specific_business_actions():
    deploy_path = Path(__file__).resolve().parents[4] / "deploy_live.sh"
    deploy_source = deploy_path.read_text()
    deploy_env_path = Path(__file__).resolve().parents[4] / "ops" / "deploy" / "deploy_env.sh"
    source = deploy_env_path.read_text()

    assert "deploy_env.sh" in deploy_source
    assert "UID=30" not in deploy_source
    assert "run_market_agent" not in source
    assert "run_macro_agent" not in source
    assert "run_technical_agent" not in source
    assert "run_setup_agent" not in source
    assert "/api/health" in source
    assert "/api/system/health" in source
    assert "tradamind_deep_health.json" in source
    assert "wait_for_backend_health" in source
    assert "health_ready=false" in source
    assert "--max-time 45" in source
    assert "json.load" in source
    assert "STRICT_DEEP_HEALTH" in source
    assert "'down', 'error'" in source or '"down", "error"' in source
    assert "pm2_delete_app()" in source
    assert 'for_each_pm2_app \\"$CORE_PM2_APPS\\" pm2_delete_app' in source or 'for_each_pm2_app \\"$BACKEND_APP\\" pm2_delete_app' in source
    assert "pm2 startOrReload $PM2_CONFIG --update-env" in source


class _FakeCursor:
    def __init__(self, prices, portfolios):
        self.prices = prices
        self.portfolios = portfolios
        self._rows = []
        self.inserted_bot_snapshots = []
        self.inserted_global_snapshots = []

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
        if "insert into portfolio_balance_snapshots" in sql_lower:
            self.inserted_global_snapshots.append(params)
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


def test_portfolio_global_snapshot_keeps_btc_value_symbol_specific(monkeypatch):
    cursor = _FakeCursor(
        prices={"BTC": 50000, "ETH": 2500},
        portfolios=[
            (101, "ETH", 100, 2, 4000, 2000, 0),
            (102, "BTC", 50, 0.1, 4500, 45000, 0),
        ],
    )
    monkeypatch.setattr(portfolio_snapshot_service, "get_db_connection", lambda: _FakeConnection(cursor))

    portfolio_snapshot_service.snapshot_all_for_user(9)

    assert len(cursor.inserted_bot_snapshots) == 2
    assert cursor.inserted_global_snapshots
    params = cursor.inserted_global_snapshots[0]
    assert params[3] == 10150  # equity: cash 150 + ETH 5000 + BTC 5000
    assert params[5] == 0.1
    assert params[6] == 5000  # btc_value_eur must not include ETH position value


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
