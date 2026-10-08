import asyncio
from types import SimpleNamespace

import pytest

from backend.schemas.technical_data_schema import (
    TechnicalIndicatorPreferenceItem,
    TechnicalIndicatorPreferenceUpdate,
)


@pytest.mark.parametrize(
    "category,indicator,api_name",
    [
        ("macro", "dxy", "macro_data_api"),
        ("technical", "rsi", "technical_data_api"),
    ],
)
def test_preference_save_dispatches_owner_scoped_history_after_commit(
    monkeypatch, category, indicator, api_name,
):
    from backend.api import macro_data_api, technical_data_api
    from backend.celery_task import celery_app as celery_module

    api = macro_data_api if api_name == "macro_data_api" else technical_data_api
    events = []

    class _Repository:
        async def replace_scope_configs(self, owner, items, **scope):
            assert owner == 17
            assert items == [(indicator, 1)]
            assert scope["symbol"] == "ETH"

        async def list_scope_configs(self, owner, **scope):
            return [SimpleNamespace(indicator=indicator, priority=1)]

    class _Session:
        async def commit(self):
            events.append("commit")

    repository = _Repository()
    if category == "macro":
        monkeypatch.setattr(macro_data_api, "MacroDataService", lambda _session: SimpleNamespace(
            preference_repository=repository,
        ))
    else:
        monkeypatch.setattr(technical_data_api, "TechnicalDataRepository", lambda _session: repository)

    monkeypatch.setattr(
        celery_module.celery_app, "send_task",
        lambda name, **kwargs: events.append((name, kwargs)),
    )
    payload = TechnicalIndicatorPreferenceUpdate(
        symbol="ETH", asset_class="crypto",
        indicators=[TechnicalIndicatorPreferenceItem(indicator=indicator, priority=1)],
    )

    if category == "macro":
        response = asyncio.run(api.put_macro_preferences(
            payload, current_user={"id": 17}, db=_Session(),
        ))
    else:
        response = asyncio.run(api.put_technical_preferences(
            payload, current_user={"id": 17}, session=_Session(),
        ))

    assert response.indicators[0].indicator == indicator
    assert events == [
        "commit",
        (
            "backend.celery_task.indicator_history_task.bootstrap_indicator_histories",
            {"kwargs": {
                "user_id": 17, "symbol": "ETH",
                "category": category, "indicator": indicator,
            }},
        ),
    ]
