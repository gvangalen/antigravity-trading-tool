import asyncio
import json

from backend.services import locale_service


def setup_function() -> None:
    locale_service._translation_cache.clear()
    locale_service._payload_translation_cache.clear()
    locale_service._translation_inflight.clear()


def test_resolve_locale_prefers_supported_account_setting():
    assert locale_service.resolve_locale({"locale": "en"}) == "en"
    assert locale_service.resolve_locale({"locale": "en-US"}) == "en"
    assert locale_service.resolve_locale({"locale": "nl"}) == "nl"
    assert locale_service.resolve_locale({"locale": "de-DE"}) == "de"
    assert locale_service.resolve_locale({"locale": "fr-FR"}) == "nl"


def test_response_language_name_uses_supported_locale_mapping():
    assert locale_service.response_language_name("nl") == "Dutch"
    assert locale_service.response_language_name("en") == "English"
    assert locale_service.response_language_name("de") == "German"
    assert locale_service.response_language_name("fr") == "fr"


def test_localize_finn_payload_keeps_dutch_without_ai(monkeypatch):
    async def fail_translate(*args, **kwargs):
        raise AssertionError("AI translation should not run for Dutch locale")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fail_translate)

    payload = {
        "response": "Voor BTC: ik zou vandaag wachten.",
        "summary": "Veilige volgende stap: Niet forceren: wacht tot de blocker-scores binnen je ranges vallen",
        "suggested_actions": ["Je kunt macro uitbreiden met Crude Oil Price (WTI)."],
    }

    localized = asyncio.run(locale_service.localize_finn_payload(payload, "nl"))

    assert localized == payload


def test_localize_finn_payload_uses_local_english_translation_without_ai(monkeypatch):
    async def fail_translate(*args, **kwargs):
        raise AssertionError("AI translation should not run for English locale")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fail_translate)

    payload = {
        "response": "Voor BTC: ik zou vandaag wachten; je setup is nog niet actief volgens je eigen ranges.",
        "summary": "Veilige volgende stap: Niet forceren: wacht tot de blocker-scores binnen je ranges vallen",
        "suggested_actions": ["Je kunt macro uitbreiden met Crude Oil Price (WTI)."],
    }

    localized = asyncio.run(locale_service.localize_finn_payload(payload, "en"))

    assert localized["response"].startswith("For BTC: I would wait today;")
    assert "your setup is not active yet according to your own ranges" in localized["response"]
    assert localized["summary"].startswith("Safe next step:")
    assert localized["suggested_actions"][0].startswith("You can expand macro with")


def test_localize_finn_payload_uses_local_german_translation_without_ai(monkeypatch):
    async def fail_translate(*args, **kwargs):
        raise AssertionError("AI translation should not run for German locale")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fail_translate)

    payload = {
        "response": "Voor BTC: ik zou vandaag wachten; je setup is nog niet actief volgens je eigen ranges.",
        "summary": "Veilige volgende stap: Niet forceren: wacht tot de blocker-scores binnen je ranges vallen",
    }

    localized = asyncio.run(locale_service.localize_finn_payload(payload, "de"))

    assert localized["response"].startswith("Fuer BTC: Ich wuerde heute warten;")
    assert "dein Setup is" in localized["response"] or "dein Setup ist" in localized["response"]
    assert localized["summary"].startswith("Sicherer naechster Schritt:")


def test_translate_text_if_needed_never_calls_ai_for_local_supported_locales(monkeypatch):
    calls = []

    async def fail_translate(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("AI translation should not run for locally supported locales")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fail_translate)

    english = asyncio.run(locale_service.translate_text_if_needed("Veilige volgende stap:", "en"))
    german = asyncio.run(locale_service.translate_text_if_needed("Veilige volgende stap:", "de"))

    assert english == "Safe next step:"
    assert german == "Sicherer naechster Schritt:"
    assert calls == []


def test_localize_finn_payload_uses_single_bundled_ai_call_for_unsupported_locale(monkeypatch):
    calls = []

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries):
        calls.append(
            {
                "prompt": prompt,
                "system_role": system_role,
                "max_tokens": max_tokens,
                "retries": retries,
                "client_max_retries": client_max_retries,
            }
        )
        assert "Translate the following Tradamind/Finn JSON payload" in prompt
        payload_json = prompt.split("\n\n", 1)[1]
        payload = json.loads(payload_json)
        payload["response"] = "FR: reponse"
        payload["summary"] = "FR: resume"
        payload["risk_summary"] = "FR: risque"
        payload["next_best_action"] = "FR: action"
        payload["review_reason"] = "FR: raison"
        payload["suggested_actions"] = ["FR: suggestion 1", "FR: suggestion 2"]
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {
        "response": "Waarom is macro zwak?",
        "summary": "Macro is zwak.",
        "risk_summary": "Voorzichtig.",
        "next_best_action": "Wacht.",
        "review_reason": "Macro blokkeert.",
        "suggested_actions": ["Actie 1", "Actie 2"],
    }

    localized = asyncio.run(locale_service.localize_finn_payload(payload, "fr"))

    assert localized["response"] == "FR: reponse"
    assert localized["summary"] == "FR: resume"
    assert localized["risk_summary"] == "FR: risque"
    assert localized["next_best_action"] == "FR: action"
    assert localized["review_reason"] == "FR: raison"
    assert localized["suggested_actions"] == ["FR: suggestion 1", "FR: suggestion 2"]
    assert len(calls) == 1
    assert calls[0]["retries"] == 1
    assert calls[0]["client_max_retries"] == 0


def test_localize_finn_payload_caches_unsupported_locale_bundle(monkeypatch):
    calls = []

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries):
        calls.append(prompt)
        payload = json.loads(prompt.split("\n\n", 1)[1])
        payload["response"] = "FR: memoized"
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {"response": "Waarom is macro zwak?"}

    first = asyncio.run(locale_service.localize_finn_payload(payload, "fr"))
    second = asyncio.run(locale_service.localize_finn_payload(payload, "fr"))

    assert first["response"] == "FR: memoized"
    assert second["response"] == "FR: memoized"
    assert len(calls) == 1


def test_localize_finn_payload_returns_original_payload_on_quota_failure(monkeypatch):
    calls = []

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries):
        calls.append(prompt)
        return "AI quota bereikt"

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {"response": "Waarom is macro zwak?", "summary": "Macro is zwak."}
    localized = asyncio.run(locale_service.localize_finn_payload(payload, "fr"))

    assert localized == payload
    assert len(calls) == 1


def test_localize_report_payload_uses_single_bundled_ai_call_for_unsupported_locale(monkeypatch):
    calls = []

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries):
        calls.append(prompt)
        payload = json.loads(prompt.split("\n\n", 1)[1])
        payload["executive_summary"] = "FR: executive"
        payload["meta_json"] = json.dumps({"macro_context": "FR: macro"}, ensure_ascii=False)
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {
        "executive_summary": "Dagrapport opent voorzichtig.",
        "meta_json": json.dumps({"macro_context": "Macro blijft kwetsbaar."}, ensure_ascii=False),
    }

    localized = asyncio.run(locale_service.localize_report_payload(payload, "fr"))

    assert localized["executive_summary"] == "FR: executive"
    assert json.loads(localized["meta_json"])["macro_context"] == "FR: macro"
    assert len(calls) == 1
