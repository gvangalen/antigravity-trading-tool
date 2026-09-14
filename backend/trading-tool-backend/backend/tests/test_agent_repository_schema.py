import asyncio

from backend.infrastructure.repositories.agent_repository import AgentRepository


class _Result:
    def fetchone(self):
        return None


class _Session:
    def __init__(self):
        self.statement = ""

    async def execute(self, statement, _params):
        self.statement = str(statement)
        return _Result()


def test_category_insight_query_uses_only_canonical_insight_columns():
    session = _Session()

    result = asyncio.run(AgentRepository(session).get_insight_by_category(9, "strategy"))

    assert result is None
    assert "created_at" not in session.statement
    assert "ORDER BY date DESC" in session.statement
