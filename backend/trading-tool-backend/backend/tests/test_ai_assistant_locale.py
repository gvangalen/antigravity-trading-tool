from backend.ai_agents.ai_assistant_prompts import get_role_prompt
from backend.services.ai_assistant_service import (
    _localized_example_text,
    _response_language_name,
)


def test_role_prompt_uses_locale_for_combined_insight_language():
    prompt = get_role_prompt(
        "combined_insight",
        {"locale": "en"},
        intent="chat",
        user_name="Gerrit",
    )

    assert "Reageer zichtbaar in English." in prompt


def test_locale_helper_returns_english_examples_when_locale_is_english():
    preferences = {"locale": "en"}

    assert _response_language_name(preferences) == "English"
    assert _localized_example_text(preferences, "no_setup", "BTC").startswith("There is no setup")
    assert _localized_example_text(preferences, "setup_type_question", "BTC") == "Do you want a DCA setup or a trade setup?"
