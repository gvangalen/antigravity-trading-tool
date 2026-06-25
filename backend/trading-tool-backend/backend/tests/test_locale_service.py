import asyncio
import json

from backend.services import locale_service


def test_resolve_locale_prefers_english_account_setting():
    assert locale_service.resolve_locale({"locale": "en"}) == "en"
    assert locale_service.resolve_locale({"locale": "en-US"}) == "en"
    assert locale_service.resolve_locale({"locale": "nl"}) == "nl"


def test_localize_finn_payload_keeps_dutch_when_locale_is_nl(monkeypatch):
    async def fail_translate(*args, **kwargs):
        raise AssertionError("translation should not run for Dutch locale")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fail_translate)

    payload = {"response": "Voor BTC: ik zou vandaag wachten.", "intent": "daily_coach"}
    localized = asyncio.run(locale_service.localize_finn_payload(payload, "nl"))

    assert localized["response"] == payload["response"]


def test_localize_finn_payload_translates_user_visible_fields(monkeypatch):
    async def fake_translate(*, prompt, system_role, max_tokens):
        assert "Voor BTC" in prompt
        return "For BTC: I would wait today."

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {"response": "Voor BTC: ik zou vandaag wachten.", "intent": "daily_coach"}
    localized = asyncio.run(locale_service.localize_finn_payload(payload, "en"))

    assert localized["response"] == "For BTC: I would wait today."


def test_translate_text_if_needed_uses_rule_based_fallback_when_ai_is_unavailable(monkeypatch):
    async def fake_translate(*, prompt, system_role, max_tokens):
        return "AI quota bereikt"

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    translated = asyncio.run(
        locale_service.translate_text_if_needed(
            "Voor BTC: ik zou vandaag wachten; je setup is nog niet actief volgens je eigen ranges.",
            "en",
        )
    )

    assert translated.startswith("For BTC: I would wait today;")
    assert "must be within" not in translated or "must be within" in translated


def test_translate_text_if_needed_cleans_up_common_report_phrases(monkeypatch):
    async def fake_translate(*, prompt, system_role, max_tokens):
        return "AI quota bereikt"

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    translated = asyncio.run(
        locale_service.translate_text_if_needed(
            "Het dagrapport voor BTC opent in late_cycle_risk, met een marktpostuur dat nu kwetsbaar aanvoelt bij een 24-uurs verandering van -3.3%. Ten opzichte van gisteren verschoof de market score met +0.0 punt. Binnen de watchlist trekt BTC nu de meeste aandacht, met een setupscore van 71 en een technische score van 53.",
            "en",
        )
    )

    assert "The daily report for BTC opens in late_cycle_risk" in translated
    assert "with a setup score of 71 and a technical score of 53" in translated
    assert "shifted by +0.0 points" in translated


def test_localize_report_payload_translates_top_level_and_meta_json(monkeypatch):
    async def fake_translate(*, prompt, system_role, max_tokens):
        if "Dagrapport opent voorzichtig." in prompt:
            return "The daily report opens cautiously."
        if "Macro blijft kwetsbaar." in prompt:
            return "Macro remains fragile."
        raise AssertionError(f"unexpected prompt: {prompt}")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {
        "executive_summary": "Dagrapport opent voorzichtig.",
        "meta_json": json.dumps({"macro_context": "Macro blijft kwetsbaar."}, ensure_ascii=False),
    }

    localized = asyncio.run(locale_service.localize_report_payload(payload, "en"))

    assert localized["executive_summary"] == "The daily report opens cautiously."
    assert json.loads(localized["meta_json"])["macro_context"] == "Macro remains fragile."
