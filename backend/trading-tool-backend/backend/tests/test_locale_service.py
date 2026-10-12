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

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries, model_override, reasoning_effort):
        calls.append(
            {
                "prompt": prompt,
                "system_role": system_role,
                "max_tokens": max_tokens,
                "retries": retries,
                "client_max_retries": client_max_retries,
                "model_override": model_override,
                "reasoning_effort": reasoning_effort,
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
    assert calls[0]["model_override"] == "gpt-6-luna"
    assert calls[0]["reasoning_effort"] == "none"


def test_localize_finn_payload_caches_unsupported_locale_bundle(monkeypatch):
    calls = []

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries, model_override, reasoning_effort):
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

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries, model_override, reasoning_effort):
        calls.append(prompt)
        return "AI quota bereikt"

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fake_translate)

    payload = {"response": "Waarom is macro zwak?", "summary": "Macro is zwak."}
    localized = asyncio.run(locale_service.localize_finn_payload(payload, "fr"))

    assert localized == payload
    assert len(calls) == 1


def test_localize_report_payload_uses_single_bundled_ai_call_for_unsupported_locale(monkeypatch):
    calls = []

    async def fake_translate(*, prompt, system_role, max_tokens, retries, client_max_retries, model_override, reasoning_effort):
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


def test_historical_report_german_translates_prose_without_rewriting_score_facts(monkeypatch):
    calls = []

    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        calls.append(fields)
        return json.dumps({key: value.replace("De markt", "Der Markt")
                           .replace("is voorzichtig bij score", "ist bei Wert")
                           for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {
        "executive_summary": "De markt is voorzichtig bij score 50.",
        "market_score": 50,
        "score_source_snapshot": {"observed_at": "2026-10-12T08:15:00Z", "assets": [
            {"symbol": "ETH", "reported_scores": {"market_score": 50}}]},
        "meta_json": json.dumps({"macro_context": "De markt is voorzichtig bij score 20.",
                                 "macro_score": 20}),
    }
    translated = asyncio.run(locale_service.localize_report_payload(original, "de"))
    assert translated["executive_summary"] == "Der Markt ist bei Wert 50."
    assert json.loads(translated["meta_json"])["macro_context"].startswith("Der Markt")
    assert translated["score_source_snapshot"] == original["score_source_snapshot"]
    assert translated["market_score"] == 50
    assert len(calls) == 1
    assert asyncio.run(locale_service.localize_report_payload(original, "de")) == translated
    assert len(calls) == 1


def test_historical_german_report_repairs_one_untranslated_section(monkeypatch):
    calls = []

    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        calls.append(fields)
        if len(fields) > 1:
            return json.dumps({"root.executive_summary": "Der Markt erreicht Wert 50.",
                               "root.market_analysis": fields["root.market_analysis"]})
        return json.dumps({"root.market_analysis": "AAPL: Keine Indikatoren eingerichtet; kein aktueller Wert."})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {
        "executive_summary": "De markt bereikt score 50.",
        "market_analysis": "AAPL: Geen indicatoren ingesteld; geen bruikbare actuele score.",
        "market_score": 50,
        "score_source_snapshot": {"content_locale": "de", "observed_at": "2026-10-12T07:20:00Z"},
    }
    localized = asyncio.run(locale_service.localize_report_payload(original, "de"))
    assert localized["executive_summary"] == "Der Markt erreicht Wert 50."
    assert localized["market_analysis"] == "AAPL: Keine Indikatoren eingerichtet; kein aktueller Wert."
    assert localized["market_score"] == 50
    assert localized["score_source_snapshot"] == original["score_source_snapshot"]
    assert len(calls) == 2


def test_report_translation_preserves_saved_setup_and_strategy_names(monkeypatch):
    calls = []

    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        calls.append(fields)
        assert all("QA Geen Score AAPL" not in value and "Mijn Vast Plan" not in value
                   for value in fields.values())
        return json.dumps({key: value.replace("De setup", "The setup")
                           .replace("De strategie", "The strategy")
                           .replace("is opgeslagen", "is saved")
                           for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {
        "executive_summary": "De setup QA Geen Score AAPL 403ee 1210 is opgeslagen.",
        "strategy_implication": "De strategie Mijn Vast Plan is opgeslagen.",
        "top_setups": [{"name": "QA Geen Score AAPL 403ee 1210", "score": 74}],
        "active_strategy": {"strategy_name": "Mijn Vast Plan"},
        "score_source_snapshot": {"content_locale": "nl", "market_score": 50},
    }
    localized = asyncio.run(locale_service.localize_report_payload(original, "en"))
    assert localized["executive_summary"] == "The setup QA Geen Score AAPL 403ee 1210 is saved."
    assert localized["strategy_implication"] == "The strategy Mijn Vast Plan is saved."
    assert localized["top_setups"] == original["top_setups"]
    assert localized["active_strategy"] == original["active_strategy"]
    assert localized["score_source_snapshot"] == original["score_source_snapshot"]
    assert len(calls) == 1


def test_report_translation_rejects_a_missing_saved_name_token(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        return json.dumps({key: "The setup was saved." for key in fields})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {
        "executive_summary": "De setup Mijn DCA Plan is opgeslagen.",
        "best_setup": {"name": "Mijn DCA Plan"},
        "score_source_snapshot": {"content_locale": "nl"},
    }
    assert asyncio.run(locale_service.localize_report_payload(original, "en")) == original


def test_report_translation_uses_watchlist_match_names_beyond_top_setups(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        assert "Plan Geen Actuele Score" not in next(iter(fields.values()))
        return json.dumps({key: value.replace("De setup", "Das Setup")
                           .replace("heeft geen score", "hat keinen Wert")
                           for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {
        "market_analysis": "De setup Plan Geen Actuele Score heeft geen score.",
        "top_setups": [{"name": "Andere setup"}],
        "watchlist": [{"symbol": "AAPL", "benchmark": {"matches": [
            {"name": "Plan Geen Actuele Score", "status": "insufficient_data"}
        ]}}],
    }
    localized = asyncio.run(locale_service.localize_report_payload(original, "de"))
    assert localized["market_analysis"] == "Das Setup Plan Geen Actuele Score hat keinen Wert."
    assert localized["watchlist"] == original["watchlist"]


def test_saved_german_today_briefing_follows_requested_language_without_storage_change(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        replacements = {
            "Guten Morgen ETH 50.": "Goedemorgen ETH 50.",
            "Der Markt ist ruhig.": "De markt is rustig.",
            "Warte auf Daten.": "Wacht op gegevens.",
            "DXY fehlt.": "DXY ontbreekt.",
        }
        return json.dumps({key: replacements[value] for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {"first_dashboard_context": {
        "content_locale": "de",
        "asset": "ETH",
        "market_snapshot": {"market_score": 50},
        "coaching_briefing": {
            "assessment": "Guten Morgen ETH 50.",
            "reasoning": "Der Markt ist ruhig.",
            "recommended_action": "Warte auf Daten.",
            "data_limitation": "DXY fehlt.",
        },
        "briefing_text": "Guten Morgen ETH 50.\nDer Markt ist ruhig.\nWarte auf Daten.\nDXY fehlt.",
    }}
    localized = asyncio.run(locale_service.localize_first_dashboard_context(original, "nl"))
    context = localized["first_dashboard_context"]
    assert context["briefing_text"].startswith("Goedemorgen ETH 50.")
    assert context["coaching_briefing"]["data_limitation"] == "DXY ontbreekt."
    assert context["market_snapshot"] == original["first_dashboard_context"]["market_snapshot"]
    assert original["first_dashboard_context"]["briefing_text"].startswith("Guten Morgen")


def test_report_translation_keeps_original_if_model_changes_a_score(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        return json.dumps({key: value.replace("50", "80") for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {"executive_summary": "Score 50/100", "market_score": 50}
    assert asyncio.run(locale_service.localize_report_payload(original, "de")) == original


def test_report_translation_rejects_dutch_prose_left_in_german_output(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        return json.dumps({key: value.replace("De markt", "Der Markt")
                           for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {"executive_summary": "De markt is voorzichtig bij score 50."}
    assert asyncio.run(locale_service.localize_report_payload(original, "de")) == original


def test_new_report_in_requested_locale_needs_no_second_translation(monkeypatch):
    async def fail(**_kwargs):
        raise AssertionError("Report was generated in German")

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", fail)
    original = {"executive_summary": "Der Markt ist vorsichtig.",
                "score_source_snapshot": {"content_locale": "de", "assets": []}}
    assert asyncio.run(locale_service.localize_report_payload(original, "de")) == original
    nested = {"report": original}
    assert asyncio.run(locale_service.localize_report_payload(nested, "de")) == nested


def test_new_german_report_can_switch_back_to_dutch(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        return json.dumps({key: value.replace("Der Markt", "De markt")
                           .replace("ist vorsichtig", "is voorzichtig")
                           for key, value in fields.items()})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    original = {"executive_summary": "Der Markt ist vorsichtig bij score 50.",
                "market_score": 50,
                "score_source_snapshot": {"content_locale": "de", "assets": []}}
    localized = asyncio.run(locale_service.localize_report_payload(original, "nl"))
    assert localized["executive_summary"] == "De markt is voorzichtig bij score 50."
    assert localized["market_score"] == 50
