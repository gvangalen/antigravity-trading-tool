import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.indicator_config_service import IndicatorConfigService


def _service(config_json):
    repository = SimpleNamespace(db=AsyncMock())
    service = IndicatorConfigService(repository)
    service.product_repository = SimpleNamespace(
        get_user_configs=AsyncMock(return_value=[SimpleNamespace(indicator="volume", config_json=config_json)]),
        set_indicator_config_metadata=AsyncMock(),
    )
    return service, repository


def test_weight_update_preserves_five_custom_buckets():
    rules = [{"range_min": index * 20, "range_max": (index + 1) * 20, "score": index * 20}
             for index in range(5)]
    service, repository = _service({"score_mode": "custom", "weight": 1, "rules": rules})

    asyncio.run(service.update_indicator_settings("market", "volume", 7, "BTC", "custom", 2))

    saved = service.product_repository.set_indicator_config_metadata.await_args.kwargs["config_json"]
    assert saved == {"score_mode": "custom", "weight": 2, "rules": rules}
    repository.db.commit.assert_awaited_once()


def test_custom_mode_without_complete_rules_cannot_replace_configuration():
    service, repository = _service({"score_mode": "custom", "rules": []})

    with pytest.raises(ValueError, match="vijf opgeslagen regels"):
        asyncio.run(service.update_indicator_settings("market", "volume", 7, "BTC", "custom", 2))

    service.product_repository.set_indicator_config_metadata.assert_not_awaited()
    repository.db.commit.assert_not_awaited()


def test_standard_mode_without_complete_template_does_not_change_benchmark():
    service, repository = _service({"score_mode": "standard"})
    repository.get_system_indicator_rules = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="indicator_score_rules_unavailable"):
        asyncio.run(service.update_indicator_settings("technical", "adx", 7, "BTC", "standard", 1))

    service.product_repository.set_indicator_config_metadata.assert_not_awaited()
    repository.db.commit.assert_not_awaited()


def test_complete_standard_template_can_be_selected():
    service, repository = _service({"score_mode": "standard"})
    repository.get_system_indicator_rules = AsyncMock(return_value=[
        SimpleNamespace(range_min=i * 20, range_max=(i + 1) * 20, is_active=True)
        for i in range(5)
    ])

    asyncio.run(service.update_indicator_settings("technical", "ma_50", 7, "BTC", "standard", 1))

    service.product_repository.set_indicator_config_metadata.assert_awaited_once()
    repository.db.commit.assert_awaited_once()


def test_existing_custom_rules_are_usable_without_system_template():
    rules = [{"range_min": i * 20, "range_max": (i + 1) * 20} for i in range(5)]
    service, repository = _service({"score_mode": "custom", "rules": rules})
    repository.get_system_indicator_rules = AsyncMock(return_value=[])

    asyncio.run(service.require_scoring_rules("technical", "volume", 7, "BTC"))

    repository.get_system_indicator_rules.assert_not_awaited()


def test_new_custom_indicator_does_not_overwrite_an_existing_configuration():
    rules = [{"range_min": i * 20, "range_max": (i + 1) * 20, "score": 50} for i in range(5)]
    service, repository = _service({"score_mode": "custom", "rules": rules})

    with pytest.raises(ValueError, match="indicator_already_configured"):
        asyncio.run(service.save_custom_rules("market", "volume", 7, "BTC", rules, 1, create_only=True))

    service.product_repository.set_indicator_config_metadata.assert_not_awaited()
    repository.db.commit.assert_not_awaited()
