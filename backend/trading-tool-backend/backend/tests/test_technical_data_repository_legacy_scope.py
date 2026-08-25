import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.domain.finn_v2_source_registry import FinnV2CanonicalSourceError
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository


class _ExecuteResult:
    def __init__(self, *, rows=None, first_row=None):
        self._rows = rows or []
        self._first_row = first_row

    def fetchall(self):
        return self._rows

    def first(self):
        return self._first_row


def _row(*, record_id: int, user_id: int, indicator: str, category: str, symbol: str):
    return SimpleNamespace(
        _mapping={
            "id": record_id,
            "user_id": user_id,
            "indicator": indicator,
            "category": category,
            "symbol": symbol,
            "asset_class": "crypto" if symbol == "BTC" else "stock",
            "priority": record_id,
            "enabled": True,
            "config_json": {},
            "provenance": "product_api",
            "source_record_id": record_id,
            "created_at": None,
            "updated_at": None,
        }
    )


def test_explicit_asset_read_never_falls_back_to_asset_class_or_default_rows():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        _ExecuteResult(rows=[]),
        _ExecuteResult(rows=[]),
        _ExecuteResult(rows=[]),
    ])
    repository = TechnicalDataRepository(session)

    configuration = asyncio.run(
        repository.get_canonical_indicator_configuration(406, symbol="BTC", asset_class="crypto")
    )

    assert configuration["technical"] == []
    assert configuration["market"] == []
    assert configuration["macro"] == []
    assert configuration["scope_by_category"] == {
        "technical": "empty",
        "market": "empty",
        "macro": "empty",
    }
    for call in session.execute.await_args_list:
        query = str(call.args[0])
        assert "symbol = :symbol" in query
        assert "symbol IS NULL" not in query
        assert call.args[1]["user_id"] == 406
        assert call.args[1]["symbol"] == "BTC"


def test_canonical_indicator_configuration_preserves_exact_owner_symbol_and_provenance():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        _ExecuteResult(rows=[_row(record_id=1, user_id=406, indicator="rsi", category="technical", symbol="BTC"), _row(record_id=2, user_id=406, indicator="ma_200", category="technical", symbol="BTC")]),
        _ExecuteResult(rows=[_row(record_id=3, user_id=406, indicator="volume", category="market", symbol="BTC")]),
        _ExecuteResult(rows=[]),
    ])
    repository = TechnicalDataRepository(session)

    configuration = asyncio.run(
        repository.get_canonical_indicator_configuration(406, symbol="BTC", asset_class="crypto")
    )

    assert [row.indicator for row in configuration["technical"]] == ["rsi", "ma_200"]
    assert [row.indicator for row in configuration["market"]] == ["volume"]
    assert configuration["storage_mode_by_category"] == {
        "technical": "canonical_asset_scoped",
        "market": "canonical_asset_scoped",
        "macro": "canonical_asset_scoped",
    }
    for row in [*configuration["technical"], *configuration["market"]]:
        assert row.user_id == 406
        assert row.symbol == "BTC"
        assert row.provenance == "product_api"
        assert row.source_record_id == row.id


def test_canonical_indicator_configuration_requires_a_user_and_asset_scope():
    repository = TechnicalDataRepository(AsyncMock())

    with pytest.raises(FinnV2CanonicalSourceError, match="missing_canonical_asset:indicator_configuration"):
        asyncio.run(repository.get_canonical_indicator_configuration(406))

    with pytest.raises(FinnV2CanonicalSourceError, match="missing_canonical_owner:indicator_configuration"):
        repository._source_registry.get("indicator_configuration").validate_request(user_id=None, symbol="BTC")


def test_new_indicator_write_requires_an_asset_scope():
    repository = TechnicalDataRepository(AsyncMock())

    with pytest.raises(FinnV2CanonicalSourceError, match="missing_canonical_asset:indicator_configuration"):
        asyncio.run(repository.ensure_user_config(406, "rsi", category="technical"))
