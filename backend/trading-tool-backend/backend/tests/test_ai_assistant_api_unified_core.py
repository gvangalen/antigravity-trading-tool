import asyncio
from unittest.mock import AsyncMock

from backend.api.ai_assistant_api import (
    _build_finn_core_rescue_envelope,
    _legacy_response_is_generic_failure,
    _legacy_response_needs_finn_rescue,
)
from backend.services.finn_plan_service import FinnPlanService


def _finn():
    return FinnPlanService(db_session=None)


def test_legacy_response_is_generic_failure_detects_default_failures():
    assert _legacy_response_is_generic_failure("⚠️ Kon geen analyse ophalen. Probeer opnieuw.")
    assert _legacy_response_is_generic_failure("Interne authenticatiefout")
    assert _legacy_response_is_generic_failure("insufficient_quota")
    assert _legacy_response_is_generic_failure("")


def test_legacy_response_needs_finn_rescue_for_generic_failure_without_action_or_draft():
    finn = _finn()

    needs_rescue = _legacy_response_needs_finn_rescue(
        finn,
        "Wat is RSI in simpele taal?",
        {"page": "/dashboard", "symbol": "BTC"},
        response_text="⚠️ Kon geen analyse ophalen. Probeer opnieuw.",
        action=None,
        draft=None,
        state={"current_flow": "education"},
    )

    assert needs_rescue is True


def test_legacy_response_needs_finn_rescue_for_non_transactional_prompt_stuck_in_bot_creation():
    finn = _finn()

    needs_rescue = _legacy_response_needs_finn_rescue(
        finn,
        "Welke strategie bekijk ik nu?",
        {"page": "/strategy", "strategy_id": 257},
        response_text="Ik help je met je bot.",
        action=None,
        draft=None,
        state={"current_flow": "bot_creation"},
    )

    assert needs_rescue is True


def test_legacy_response_does_not_rescue_real_transactional_request():
    finn = _finn()

    needs_rescue = _legacy_response_needs_finn_rescue(
        finn,
        "Maak een bot voor mijn BTC setup",
        {"page": "/bot", "symbol": "BTC"},
        response_text="Ik ga je helpen een bot te maken.",
        action=None,
        draft=None,
        state={"current_flow": "bot_creation"},
    )

    assert needs_rescue is False


def test_build_finn_core_rescue_envelope_prefers_education_builder():
    finn = _finn()
    finn.build_education_response = AsyncMock(return_value={"intent": "education", "flow": "education"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat is RSI in simpele taal?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_education_response.assert_awaited_once()
    assert response["intent"] == "education"


def test_build_finn_core_rescue_envelope_prefers_context_explain_builder():
    finn = _finn()
    finn.build_context_explain_response = AsyncMock(return_value={"intent": "context_explain", "flow": "context_explain"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Leg mijn setup uit",
            context_payload={"page": "/setup", "setup_id": 62, "symbol": "BTC"},
        )
    )

    finn.build_context_explain_response.assert_awaited_once()
    assert response["intent"] == "context_explain"


def test_build_finn_core_rescue_envelope_prefers_product_help_builder():
    finn = _finn()
    finn.build_product_help_response = AsyncMock(return_value={"intent": "product_help", "flow": "product_help"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat kan ik hier doen?",
            context_payload={"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
        )
    )

    finn.build_product_help_response.assert_awaited_once()
    assert response["intent"] == "product_help"


def test_build_finn_core_rescue_envelope_prefers_behavioral_builder():
    finn = _finn()
    finn.build_behavioral_intelligence_response = AsyncMock(
        return_value={"intent": "behavioral_intelligence", "flow": "behavioral_intelligence"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Ik voel FOMO, wat moet ik doen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_behavioral_intelligence_response.assert_awaited_once()
    assert response["intent"] == "behavioral_intelligence"
