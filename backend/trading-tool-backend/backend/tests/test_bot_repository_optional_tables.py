from datetime import date
import asyncio
from unittest.mock import AsyncMock

from backend.infrastructure.repositories.bot_repository import BotRepository


def test_get_bot_decisions_by_date_skips_query_when_optional_table_is_absent():
    async def run():
        session = AsyncMock()
        repository = BotRepository(session)
        repository.check_table_exists = AsyncMock(return_value=False)

        result = await repository.get_bot_decisions_by_date(7, date(2026, 9, 17))

        assert result == []
        session.execute.assert_not_awaited()

    asyncio.run(run())
