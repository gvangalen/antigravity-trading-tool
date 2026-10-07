import asyncio

from backend.infrastructure.repositories.strategy_repository import StrategyRepository


def test_strategy_reads_confirmed_owner_fields_not_legacy_ai_snapshot():
    class Result:
        def fetchall(self):
            return []

    class Session:
        async def execute(self, statement, params):
            sql = str(statement)
            assert "s.entry::text as entry" in sql
            assert "s.stop_loss::text as stop_loss" in sql
            assert "array_to_string(s.targets, ',') as targets" in sql
            assert "active_strategy_snapshot" not in sql
            assert "st.user_id = s.user_id" in sql
            assert params == {"user_id": 7, "setup_id": 31}
            return Result()

    assert asyncio.run(StrategyRepository(Session()).query_strategies(7, {"setup_id": 31})) == []
