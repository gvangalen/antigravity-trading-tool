import asyncio

import backend.infrastructure.repositories.assistant_context_repository as assistant_context_module
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


def test_configured_indicator_context_delegates_to_canonical_symbol_scoped_repository(monkeypatch):
    class _CanonicalRepository:
        def __init__(self, session):
            self.session = session

        async def get_configured_indicator_names(self, user_id, *, symbol):
            assert user_id == 344
            assert symbol == "BTC"
            return {"market": ["ema_20"], "macro": [], "technical": ["RSI"]}

    monkeypatch.setattr(assistant_context_module, "TechnicalDataRepository", _CanonicalRepository)

    result = asyncio.run(AssistantContextRepository(object())._configured_indicator_context(344, "BTC"))

    assert result == {"market": ["ema_20"], "macro": [], "technical": ["RSI"]}
