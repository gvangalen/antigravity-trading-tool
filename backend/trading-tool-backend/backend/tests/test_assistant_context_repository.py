import asyncio

from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository


class _FakeScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class _FakeColumnResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return _FakeScalarResult(self._values)


class _FakeMappingsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeQueryResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return _FakeMappingsResult(self._rows)


class _FakeAssistantContextSession:
    def __init__(self, columns, rows):
        self.columns = list(columns)
        self.rows = list(rows)
        self.executed = []

    async def execute(self, query, params=None):
        sql = str(query)
        self.executed.append({"sql": sql, "params": params or {}})
        if "information_schema.columns" in sql:
            return _FakeColumnResult(self.columns)
        return _FakeQueryResult(self.rows)


def test_configured_indicator_context_skips_enabled_filter_when_column_is_absent():
    session = _FakeAssistantContextSession(
        columns=["user_id", "indicator", "category", "priority", "symbol"],
        rows=[
            {"category": "technical", "indicator": "rsi"},
            {"category": "market", "indicator": "ema_20"},
        ],
    )
    repo = AssistantContextRepository(session)

    result = asyncio.run(repo._configured_indicator_context(344, "BTC"))

    assert result == {
        "market": ["ema_20"],
        "macro": [],
        "technical": ["RSI"],
    }
    executed_sql = session.executed[1]["sql"]
    assert "enabled = TRUE" not in executed_sql
    assert "symbol = :symbol" in executed_sql
    assert session.executed[1]["params"] == {"user_id": 344, "category": "technical", "symbol": "BTC"}


def test_configured_indicator_context_probe_failure_uses_legacy_safe_columns():
    class _ProbeFailureSession:
        def __init__(self):
            self.executed = []

        async def execute(self, query, params=None):
            sql = str(query)
            self.executed.append({"sql": sql, "params": params or {}})
            if "information_schema.columns" in sql:
                raise RuntimeError("probe failed")
            return _FakeQueryResult(
                [
                    {"category": "technical", "indicator": "rsi"},
                    {"category": "macro", "indicator": "fear_greed_index"},
                ]
            )

    session = _ProbeFailureSession()
    repo = AssistantContextRepository(session)

    result = asyncio.run(repo._configured_indicator_context(344, "BTC"))

    assert result == {
        "market": [],
        "macro": ["fear_greed_index"],
        "technical": ["RSI"],
    }
    executed_sql = session.executed[1]["sql"]
    assert "enabled = TRUE" not in executed_sql
    assert "priority ASC" not in executed_sql
    assert "symbol = :symbol" not in executed_sql
