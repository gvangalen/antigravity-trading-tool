from datetime import date
import asyncio
from unittest.mock import AsyncMock
from pathlib import Path

from backend.infrastructure.repositories.bot_repository import BotRepository


def test_bot_reads_never_fall_back_to_btc_when_relational_asset_is_missing():
    source = Path(BotRepository.__module__.replace(".", "/") + ".py")
    repository_source = (Path(__file__).resolve().parents[1] / source.relative_to("backend")).read_text()

    assert "COALESCE(s.symbol, s.data->>'symbol', st.symbol, 'BTC')" not in repository_source


def test_get_bot_decisions_by_date_skips_query_when_optional_table_is_absent():
    async def run():
        session = AsyncMock()
        repository = BotRepository(session)
        repository.check_table_exists = AsyncMock(return_value=False)

        result = await repository.get_bot_decisions_by_date(7, date(2026, 9, 17))

        assert result == []
        session.execute.assert_not_awaited()

    asyncio.run(run())
