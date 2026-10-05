import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.schemas.assistant_schema import AssistantPreferenceUpdate
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_tool_adapters.profile_tool_adapter import ProfileToolAdapter


def test_optional_trader_context_accepts_clear_and_rejects_oversize():
    assert AssistantPreferenceUpdate(trader_context="").trader_context == ""
    assert AssistantPreferenceUpdate(trader_context="x" * 1000).trader_context == "x" * 1000
    with pytest.raises(ValidationError):
        AssistantPreferenceUpdate(trader_context="x" * 1001)


def test_owner_profile_read_exposes_saved_context_as_typed_evidence():
    adapter = ProfileToolAdapter(session=object())

    async def get_by_id(user_id):
        assert user_id == 41
        return SimpleNamespace(ai_preferences={"trader_context": "  Laat mij bij FOMO eerst afkoelen.  "})

    adapter.users.get_by_id = get_by_id
    result = asyncio.run(adapter.execute(user_id=41))

    assert result["data"].trader_context == "Laat mij bij FOMO eerst afkoelen."
    assert result["data"].has_profile is True
    assert "trader_context" in result["summary"]["keys"]
    assert FinnV2ReasoningContextService(session=object())._sanitize_facts(
        result["data"].dict(), "read_profile"
    )["trader_context"] == result["data"].trader_context
