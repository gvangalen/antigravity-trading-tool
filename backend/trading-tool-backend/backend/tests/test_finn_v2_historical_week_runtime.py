from types import SimpleNamespace

from backend.services.finn_v2_run_service import _minimal_read_answer as _runtime_minimal_read_answer


QUESTION = (
    "Bespreek mijn afgesloten AAPL Paper-trade van 12 november en de opgeslagen "
    "weekreflectie van 9–15 november. Welke exitreden en welk concreet aandachtspunt "
    "zijn bevestigd, en wat blijft onzeker over plantrouw? Noem de bronmomenten "
    "apart. Lees alleen; wijzig niets."
)


LEGACY_QUESTION = QUESTION.replace(
    "Welke exitreden en welk concreet aandachtspunt zijn bevestigd, en wat blijft onzeker over plantrouw? ",
    "Noem de opgeslagen exitreden. ",
)


def _minimal_read_answer(**kwargs):
    # Keep the legacy source-completion assertions in this file while the
    # production path uses typed rendering for the combined historical read.
    return _runtime_minimal_read_answer(_legacy_historical_test=True, **kwargs)

def _prepared(*, text, trade_date="2026-11-12T15:02:00+00:00", week=True):
    return SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text=text, uses_previous_response=False, turn_contract=None,
            tool_trace=({"name": "get_review_history", "result": {"results": [{
                "scope": "read_review_history", "status": "completed",
                "source": "bot_decisions_and_finn_trade_reviews",
                "data": {
                    "weekly_reflection": ({
                        "week_start": "2026-11-09", "week_end": "2026-11-15",
                        "generated_at": "2026-11-16T05:15:00+00:00",
                        "time_zone": "Europe/Amsterdam",
                    } if week else None),
                    "closed_trades": [{
                        "review_id": 2127, "symbol": "AAPL", "environment": "paper",
                        "bot_id": 129,
                        "exit_at": trade_date,
                        "paper_exit_decision_at": "2026-11-12T14:59:00+00:00",
                        "paper_exit_evidence": {
                            "trigger": "first_target",
                            "execution_fx_eur_per_unit": 0.92,
                            "execution_fx_observed_at": "2026-11-12T14:02:00+00:00",
                        },
                    }],
                },
            }]}},),
        ),
    )


def test_minimal_live_read_completes_historical_exit_and_week_in_user_zone():
    for text in (
        "Exitreden: eerste koersdoel. Tradebeslissing: 12 november 14:59 UTC. "
        "Weekreflectie opgeslagen: 16 november 05:15 UTC.",
        "De AAPL Paper-exit raakte het eerste doel; controleer het oorspronkelijke "
        "plan. 14:59 UTC en 05:15 UTC zijn de bronmomenten.",
    ):
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=_prepared(text=text),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        # The recorded close is distinct from the model's 14:59 UTC decision.
        assert "AAPL Paper-trade als gesloten geregistreerd: 2026-11-12 16:02:00 CET" in answer.text
        assert "Geverifieerd opslagmoment week 2026-11-09 t/m 2026-11-15: 2026-11-16 06:15:00 CET" in answer.text


def test_historical_paper_bot_clock_is_not_compared_with_newer_bot_check():
    prepared = _prepared(text=(
        "Historische botbeslissing voor AAPL: 12 november 2026 14:59 UTC. "
        "De Paper-uitstap raakte het eerste koersdoel; volledige plantrouw blijft onzeker."
    ))
    prepared.response.tool_trace[0]["result"]["results"][0]["data"]["latest_bot_decisions"] = [{
        "bot_id": 129, "symbol": "AAPL", "decision_at": "2026-11-27T18:48:00+00:00",
    }]
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "12 november 2026 14:59 UTC" in answer.text
    assert "Geverifieerd FX-bronmoment" in answer.text


def test_historical_exit_decision_compounds_cannot_claim_registered_close_clock():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="De uitstapbeslissing op 12 november 2026 om 15:00:30 UTC.")
    evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
    for label in ("uitstapbeslissing", "exitbeslissing", "Paper-exitbeslissing"):
        wrong = f"De {label} op 12 november 2026 om 15:00:30 UTC."
        assert not current_source_moments_supported(
            wrong, evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
        ), label
    assert current_source_moments_supported(
        "De uitstapbeslissing op 12 november 2026 om 14:59 UTC.",
        evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
    )


def test_historical_quote_source_and_decision_are_separate_clocks():
    prepared = _prepared(text="Onjuist modelantwoord.", trade_date="2026-11-12T15:00:30+00:00")
    trade = prepared.response.tool_trace[0]["result"]["results"][0]["data"]["closed_trades"][0]
    trade["paper_exit_decision_at"] = "2026-11-12T15:00:30+00:00"
    trade["paper_exit_evidence"].update({
        "source_price_currency": "USD", "source_price": 358.60,
        "source_price_at": "2026-11-12T14:59:00+00:00",
        "execution_source_price": 320.25,
        "execution_source_price_currency": "EUR",
        "execution_source_price_at": "2026-11-12T14:59:00+00:00",
    })
    hostile_drafts = (
        "De uitvoeringskoers was 999 USD om 14:59 UTC.",
        "De uitvoeringskoers was -320,25 EUR.",
        "De uitvoeringskoers was 320,25 GBP.",
        "De uitvoeringskoers was €999,00.",
        "De verkoop werd uitgevoerd tegen 999 USD.",
        "Voor bot #456: uitvoeringskoers 999 USD.",
        "Op 12 november 2026 om 14:58 UTC werd de uitvoeringskoers vastgelegd.",
        "Zowel de uitvoeringskoers als de exitbeslissing: 15:00:30 UTC.",
    )
    baseline = None
    for draft in hostile_drafts:
        prepared.response.text = draft
        answer = _runtime_minimal_read_answer(
            message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert answer.text == (baseline or answer.text)
        baseline = answer.text
        assert draft not in answer.text
        assert "999" not in answer.text
        assert "GBP" not in answer.text
        assert "bot #456" not in answer.text
        assert "Koersbron bij exitbeoordeling: 358,60 USD; bronmoment 2026-11-12 15:59:00 CET" in answer.text
        assert "Koersbron bij Paper-uitvoering: 320,25 EUR; bronmoment 2026-11-12 15:59:00 CET" in answer.text
        assert "Botbeslissing: 2026-11-12 16:00:30 CET" in answer.text
        assert "Paper-sluiting geregistreerd: 2026-11-12 16:00:30 CET" in answer.text
        assert "Weekreflectie 2026-11-09 t/m 2026-11-15 opgeslagen: 2026-11-16 06:15:00 CET" in answer.text

    trade["paper_exit_evidence"]["execution_source_price_currency"] = "USD"
    changed = _runtime_minimal_read_answer(
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert changed.status == "completed", changed.reason
    assert "320,25 USD" in changed.text
    trade.pop("paper_exit_decision_at")
    missing_decision = _runtime_minimal_read_answer(
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert missing_decision.status == "unavailable"


def test_historical_week_typed_answer_uses_user_zone_and_confirmed_lesson():
    prepared = _prepared(text="De uitvoeringskoers was -999 GBP.")
    trade = prepared.response.tool_trace[0]["result"]["results"][0]["data"]["closed_trades"][0]
    trade["paper_exit_evidence"].update({
        "source_price_currency": "USD", "source_price": 358.60,
        "source_price_at": "2026-11-12T14:59:00+00:00",
        "execution_source_price": 320.25,
        "execution_source_price_currency": "EUR",
        "execution_source_price_at": "2026-11-12T14:59:00+00:00",
    })
    trade["confirmed_lesson"] = {
        "lesson_text": "Controleer bij de volgende exit de oorspronkelijke stop en het eerste doel.",
        "confirmed_at": "2026-11-13T09:07:57+00:00",
    }
    answer = _runtime_minimal_read_answer(
        message=QUESTION, prepared=prepared, user_time_zone="America/New_York",
    )
    assert answer.status == "completed", answer.reason
    assert "09:59:00 EST (America/New_York)" in answer.text
    assert "10:02:00 EST (America/New_York)" in answer.text
    assert "00:15:00 EST (America/New_York)" in answer.text
    assert "Door gebruiker bevestigde les (2026-11-13 04:07:57 EST)" in answer.text
    assert "-999" not in answer.text
    assert "GBP" not in answer.text


def test_historical_week_without_typed_quote_reports_missing_source():
    for message in (
        QUESTION,
        QUESTION.replace("welk concreet aandachtspunt", "welke concrete aandachtspunten"),
        QUESTION.replace("weekreflectie", "wekelijkse reflectie"),
        QUESTION.replace("afgesloten AAPL Paper-trade", "gesloten AAPL Paper-trade"),
    ):
        answer = _runtime_minimal_read_answer(
            message=message,
            prepared=_prepared(text="De verkoopprijs bedroeg 999 USD."),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert "Koersbron bij Paper-uitvoering: prijs, valuta of bronmoment niet verifieerbaar" in answer.text
        assert "999 USD" not in answer.text
    english_locale = _prepared(text="De verkoopprijs bedroeg 999 USD.")
    english_locale.locale = "en"
    answer = _runtime_minimal_read_answer(
        message=QUESTION, prepared=english_locale, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "999 USD" not in answer.text


def test_historical_week_typed_answer_rejects_other_bot_or_dossier():
    prepared = _prepared(text="Het eerste koersdoel werd geraakt.")
    for extra in ("Gebruik uitsluitend de trade van bot #456.",
                  "Gebruik uitsluitend dossier 999.", "Gebruik uitsluitend dossier #999."):
        answer = _runtime_minimal_read_answer(
            message=f"{QUESTION} {extra}", prepared=prepared,
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "unavailable", extra


def test_historical_week_respects_week_only_and_live_only_scope():
    prepared = _prepared(text="De verkoopprijs bedroeg 999 USD.")
    week_only = _runtime_minimal_read_answer(
        message="Vat alleen mijn opgeslagen weekreflectie van 9–15 november samen; "
                "laat individuele trades buiten beschouwing.",
        prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert week_only.status == "completed", week_only.reason
    assert "zonder details over individuele trades" in week_only.text
    assert "Paper-exit" not in week_only.text
    assert "999 USD" not in week_only.text

    negated_exit = _runtime_minimal_read_answer(
        message="Bespreek niet mijn AAPL Paper-exit, maar alleen de weekreflectie van "
                "9–15 november.",
        prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert negated_exit.status == "completed", negated_exit.reason
    assert "Paper-exit" not in negated_exit.text
    assert "999 USD" not in negated_exit.text

    live_only = _runtime_minimal_read_answer(
        message=f"{QUESTION} Gebruik alleen Live-gegevens, geen Paper-trades.",
        prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert live_only.status == "unavailable"
    assert "999 USD" not in live_only.text
    exclusive_live = _runtime_minimal_read_answer(
        message=f"{QUESTION} Gebruik uitsluitend Live-gegevens.",
        prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert exclusive_live.status == "unavailable"

    other_week = "2–8 november"
    for message in (
        QUESTION.replace("9–15 november", other_week),
        "Vat alleen mijn opgeslagen weekreflectie van 2–8 november samen; "
        "laat individuele trades buiten beschouwing.",
        "Summarize my weekly review from 2 to 8 November 2026.",
    ):
        mismatch = _runtime_minimal_read_answer(
            message=message, prepared=prepared, user_time_zone="Europe/Amsterdam",
        )
        assert mismatch.status == "unavailable", message
        assert "999 USD" not in mismatch.text

    excluded_week = _runtime_minimal_read_answer(
        message="Toon niet mijn weekreflectie; leg uit wat plantrouw betekent.",
        prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert excluded_week.status == "unavailable"
    assert "999 USD" not in excluded_week.text
    assert "Opgeslagen weekreflectie" not in excluded_week.text


def test_historical_aapl_paper_renderer_does_not_capture_other_asset_or_live():
    prepared = _prepared(text="Het ETH-dossier wordt via de gewone read-route beoordeeld.")
    for message in (
        "Bespreek mijn afgesloten ETH Paper-trade van 12 november en de opgeslagen "
        "weekreflectie van 9–15 november. Lees alleen.",
        "Bespreek mijn afgesloten AAPL Live-trade van 12 november en de opgeslagen "
        "weekreflectie van 9–15 november. Lees alleen.",
    ):
        answer = _runtime_minimal_read_answer(
            message=message, prepared=prepared, user_time_zone="Europe/Amsterdam",
        )
        assert answer.reason != "historical_week_exit_evidence_unavailable", message
        assert "AAPL Paper-exit" not in answer.text


def test_english_historical_week_without_read_is_unavailable():
    prepared = _prepared(text="The execution price was 999 USD.", week=False)
    prepared.locale = "en"
    answer = _runtime_minimal_read_answer(
        message="Discuss my closed AAPL Paper trade and weekly reflection, "
                "including the exit reason and source moments. Read only.",
        prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "unavailable"
    assert "999 USD" not in answer.text
    assert "999" not in answer.text


def test_live_week_saved_clock_and_fx_markdown_are_sanitized():
    prepared = _prepared(text=(
        "Opgeslagen weekreflectie voor 9–15 november 2026: gegenereerd "
        "16 november 2026, 05:15:00 CET (Amsterdamse tijd).\n"
        "- **FX-bronmoment:** 12 november 2026, 14:03 UTC"
    ))
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "05:15:00 CET" not in answer.text
    assert "06:15:00 CET" in answer.text
    assert "- **FX-brontijd" not in answer.text
    assert "FX-brontijd: zie de afzonderlijk geverifieerde bronregel" in answer.text


def test_live_combined_answer_keeps_three_distinct_source_moments():
    prepared = _prepared(text=(
        "Exitbeslissing en USD-koers van 358,60: 12 november 2026, 14:59:00 UTC. "
        "Opgeslagen weekreflectie voor 9–15 november 2026: gegenereerd "
        "16 november 2026, 05:15:00 CET (Amsterdamse tijd).\n"
        "- **FX-bronmoment:** 12 november 2026, 14:03 UTC"
    ), trade_date="2026-11-12T15:00:30+00:00")
    trade = prepared.response.tool_trace[0]["result"]["results"][0]["data"]["closed_trades"][0]
    trade["paper_exit_decision_at"] = "2026-11-12T15:00:30+00:00"
    trade["paper_exit_evidence"].update({
        "source_price_currency": "USD", "source_price": 358.60,
        "source_price_at": "2026-11-12T14:59:00+00:00",
        "execution_source_price": 358.60,
        "execution_source_price_currency": "USD",
        "execution_source_price_at": "2026-11-12T14:59:00+00:00",
    })
    answer = _runtime_minimal_read_answer(
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "Koersbron bij exitbeoordeling: 358,60 USD; bronmoment 2026-11-12 15:59:00 CET" in answer.text
    assert "2026-11-12 15:02:00 CET" in answer.text  # separate FX source
    assert "2026-11-12 16:00:30 CET" in answer.text  # decision and close may coincide
    assert "2026-11-16 06:15:00 CET" in answer.text  # saved week
    assert "05:15:00 CET" not in answer.text
    assert "**FX-brontijd" not in answer.text


def test_historical_exit_decision_completion_repairs_wrong_close_label_and_adds_missing_decision():
    for draft in (
        "De uitstapbeslissing op 12 november 2026 om 15:00:30 UTC. "
        "Het eerste koersdoel werd geraakt; volledige plantrouw blijft onzeker.",
        "De exitbeslissing op 12 november 2026, 15:00:30 UTC. "
        "Het eerste koersdoel werd geraakt; volledige plantrouw blijft onzeker.",
        "Het eerste koersdoel werd geraakt; volledige plantrouw blijft onzeker.",
    ):
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=_prepared(
                text=draft, trade_date="2026-11-12T15:00:30+00:00",
            ),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert "Paper-exitbeslissing: 2026-11-12 15:59:00 CET" in answer.text
        assert "15:00:30 UTC" not in answer.text
        assert "AAPL Paper-trade als gesloten geregistreerd: 2026-11-12 16:00:30 CET" in answer.text


def test_historical_exit_decision_completion_needs_unique_owner_read_decision():
    prepared = _prepared(text="De uitstapbeslissing op 12 november 2026 om 15:00:30 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    row["data"]["closed_trades"][0].pop("paper_exit_decision_at")
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "unavailable"
    assert "Paper-exitbeslissing: 2026-11-12" not in answer.text


def test_historical_exit_decision_completion_does_not_select_between_two_same_day_trades():
    prepared = _prepared(text="De uitstapbeslissing op 12 november 2026 om 15:00:30 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    trade = row["data"]["closed_trades"][0]
    row["data"]["closed_trades"].append({
        **trade, "review_id": 2128, "exit_at": "2026-11-12T18:00:00+00:00",
        "paper_exit_decision_at": "2026-11-12T17:59:00+00:00",
    })
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "unavailable"
    assert "Geverifieerde AAPL Paper-exitbeslissing" not in answer.text


def test_historical_exit_decision_repair_does_not_relabel_a_report_clock():
    draft = "De exitbeslissing volgt het rapportmoment 12 november 2026 05:15 UTC."
    prepared = _prepared(text=draft)
    evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments

    completed = complete_historical_week_exit_moments(
        draft, evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
    )
    assert "het rapportmoment 12 november 2026 05:15 UTC" in completed
    assert "het rapportmoment 2026-11-12 15:59:00 CET" not in completed
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    if answer.status == "completed":
        assert "het rapportmoment 12 november 2026 05:15 UTC" in answer.text


def test_historical_exit_decision_repair_does_not_relabel_an_earlier_trade():
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments
    for draft in (
        "De exitbeslissing van een eerdere AAPL-trade was op 5 november 2026 14:59 UTC.",
        "Voor een eerdere AAPL-trade: exitbeslissing op 5 november 2026 om 14:00 UTC.",
        "Voor een eerdere AAPL-trade: exitbeslissing op 12 november 2026 om 14:00 UTC.",
        "De exitbeslissing op 12 november 2026 om 14:00 UTC hoort bij een eerdere AAPL-trade.",
        "Voor de AAPL-ochtendtrade: exitbeslissing op 12 november 2026 om 10:00 UTC.",
        "Voor de AAPL-ochtendtrade: exitbeslissing op 12 november 2026 om 15:00:30 UTC.",
    ):
        prepared = _prepared(text=draft, trade_date="2026-11-12T15:00:30+00:00")
        evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
        completed = complete_historical_week_exit_moments(
            draft, evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
        )
        assert draft in completed
        assert "eerdere AAPL-trade: exitbeslissing op 2026-11-12 15:59" not in completed
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "unavailable"


def test_historical_exit_decision_only_repairs_exact_registered_close_clock():
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments

    for clock in ("10:00:00 UTC", "15:00 UTC", "15:00:31 UTC"):
        draft = f"De exitbeslissing op 12 november 2026 om {clock}."
        prepared = _prepared(text=draft, trade_date="2026-11-12T15:00:30+00:00")
        evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
        completed = complete_historical_week_exit_moments(
            draft, evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
        )
        assert draft in completed
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "unavailable"


def test_model_written_fx_fallback_phrase_does_not_bypass_clock_scrub():
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments

    prepared = _prepared(text=(
        "FX-brontijd: zie de afzonderlijk geverifieerde bronregel 12 november 14:03 UTC, "
        "botbeslissing 12 november 14:59 UTC."
    ))
    evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
    completed = complete_historical_week_exit_moments(
        prepared.response.text, evidence, question=LEGACY_QUESTION,
        user_time_zone="Europe/Amsterdam",
    )
    assert "14:03 UTC" not in completed
    assert "botbeslissing 12 november 14:59 UTC" in completed


def test_historical_bot_clock_requires_typed_owner_bound_exit_decision():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="Historische botbeslissing voor AAPL: 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    row["data"]["latest_bot_decisions"] = [{
        "bot_id": 129, "symbol": "AAPL", "decision_at": "2026-11-27T18:48:00+00:00",
    }]
    assert current_source_moments_supported(
        prepared.response.text, (row,), question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
    )
    row["data"]["closed_trades"][0].pop("paper_exit_decision_at")
    assert not current_source_moments_supported(
        prepared.response.text, (row,), question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
    )


def test_historical_clock_cannot_be_attributed_to_another_closed_trade():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="Bij trade #2128 was de botbeslissing 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    other = {**row["data"]["closed_trades"][0], "review_id": 2128,
             "exit_at": "2026-11-12T18:00:00+00:00",
             "paper_exit_decision_at": "2026-11-12T17:59:00+00:00"}
    row["data"]["closed_trades"].append(other)
    row["data"]["latest_bot_decisions"] = [{
        "bot_id": 129, "symbol": "AAPL", "decision_at": "2026-11-27T18:48:00+00:00",
    }]
    assert not current_source_moments_supported(
        prepared.response.text, (row,), question="Bespreek trade #2128 voor AAPL.",
        user_time_zone="Europe/Amsterdam",
    )
    assert not current_source_moments_supported(
        "Historische botbeslissing bij dossier #2128: 27 november 2026 18:48 UTC.",
        (row,), question="Bespreek dossier #2128 voor AAPL.",
        user_time_zone="Europe/Amsterdam",
    )
    assert not current_source_moments_supported(
        "Bij dossier #999 was de botbeslissing 12 november 2026 14:59 UTC.",
        (row,), question="Bespreek dossier #999 voor AAPL.",
        user_time_zone="Europe/Amsterdam",
    )
    assert not current_source_moments_supported(
        "De botbeslissing voor AAPL was 12 november 2026 14:59 UTC.",
        (row,), question="Bespreek mijn AAPL-trades van 12 november.",
        user_time_zone="Europe/Amsterdam",
    )
    assert not current_source_moments_supported(
        "Bij dossier #2127 was de botbeslissing 12 november 2026 14:59 UTC.",
        (row,), question="Bespreek mijn afgesloten AAPL-trade van 12 november.",
        user_time_zone="Europe/Amsterdam",
    )


def test_conflicting_reads_for_same_closed_review_do_not_verify_a_bot_clock():
    from copy import deepcopy
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="Bij dossier #2127 was de botbeslissing 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    conflict = deepcopy(row)
    conflict["data"]["closed_trades"][0]["paper_exit_decision_at"] = "2026-11-12T14:58:00+00:00"
    assert not current_source_moments_supported(
        prepared.response.text, (row, conflict), question="Bespreek dossier #2127 voor AAPL.",
        user_time_zone="Europe/Amsterdam",
    )


def test_historical_trade_date_uses_the_users_zone_only():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="De botbeslissing voor de AAPL-trade van 12 november was 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    row["data"]["closed_trades"][0]["exit_at"] = "2026-11-12T23:30:00+00:00"
    question = "Bespreek mijn afgesloten AAPL-trade van 12 november."
    assert not current_source_moments_supported(
        prepared.response.text, (row,), question=question,
        user_time_zone="Europe/Amsterdam",
    )
    assert current_source_moments_supported(
        prepared.response.text, (row,), question=question,
        user_time_zone="UTC",
    )
    assert not current_source_moments_supported(
        prepared.response.text, (row,), question=question,
    )


def test_historical_iso_date_and_named_asset_must_match_the_closed_dossier():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="Historische botbeslissing voor AAPL: 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    assert not current_source_moments_supported(
        prepared.response.text, (row,),
        question="Bespreek mijn afgesloten AAPL-trade van 2026-11-05.",
        user_time_zone="Europe/Amsterdam",
    )
    assert not current_source_moments_supported(
        prepared.response.text, (row,),
        question="Bespreek mijn afgesloten AAPL-trade van 05/11/2026.",
        user_time_zone="Europe/Amsterdam",
    )
    assert not current_source_moments_supported(
        "Historische botbeslissing voor MSFT: 12 november 2026 14:59 UTC.",
        (row,), question="Bespreek mijn afgesloten MSFT-trade van 12 november.",
        user_time_zone="Europe/Amsterdam",
    )
    assert current_source_moments_supported(
        prepared.response.text, (row,),
        question="Bespreek mijn afgesloten AAPL-trade van 2026-11-12.",
        user_time_zone="Europe/Amsterdam",
    )


def test_model_named_asset_cannot_choose_between_two_user_trades():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="De historische AAPL-botbeslissing was 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    row["data"]["closed_trades"].append({
        **row["data"]["closed_trades"][0], "review_id": 3000, "symbol": "MSFT",
        "paper_exit_decision_at": "2026-11-12T14:58:00+00:00",
    })
    assert not current_source_moments_supported(
        prepared.response.text, (row,),
        question="Bespreek mijn afgesloten trade van 12 november.",
        user_time_zone="Europe/Amsterdam",
    )


def test_trade_without_decision_evidence_still_counts_for_ambiguity():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="De historische AAPL-botbeslissing was 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    row["data"]["closed_trades"].append({
        **row["data"]["closed_trades"][0], "review_id": 3000,
        "paper_exit_decision_at": None, "paper_exit_evidence": None,
    })
    assert not current_source_moments_supported(
        prepared.response.text, (row,),
        question="Bespreek mijn afgesloten AAPL-trade van 12 november.",
        user_time_zone="Europe/Amsterdam",
    )


def test_historical_exit_clock_cannot_replace_current_bot_clock():
    from backend.services.finn_v2_source_moment_claims import current_source_moments_supported

    prepared = _prepared(text="De laatste botbeslissing voor AAPL was 12 november 2026 14:59 UTC.")
    row = prepared.response.tool_trace[0]["result"]["results"][0]
    row["data"]["latest_bot_decisions"] = [{
        "bot_id": 129, "symbol": "AAPL", "decision_at": "2026-11-27T18:48:00+00:00",
    }]
    assert not current_source_moments_supported(
        prepared.response.text, (row,), question="Wat was de laatste AAPL-botbeslissing?",
    )


def test_minimal_live_read_does_not_complete_mismatched_or_missing_sources():
    text = "De AAPL-exit en weekreflectie zijn besproken."
    for prepared in (_prepared(text=text, trade_date="2026-11-05T14:59:00+00:00"),
                     _prepared(text=text, week=False)):
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=prepared,
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert "als gesloten geregistreerd" not in answer.text


def test_minimal_live_read_corrects_only_week_storage_clock():
    draft = (
        "Exitreden: eerste koersdoel. Botbeslissing: 12 november 14:59 UTC. "
        "Paper-uitvoering: 12 november 14:59 UTC. FX-bron: 12 november 14:02 UTC. "
        "Opgeslagen weekreflectie gegenereerd: 16 november 2026, 05:15:00 CET. "
        "Lesbevestiging: 13 november 09:07:57 UTC."
    )
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=_prepared(text=draft),
        user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "Opslagmoment van deze weekreflectie niet geverifieerd" in answer.text
    assert "Geverifieerd opslagmoment week 2026-11-09 t/m 2026-11-15: 2026-11-16 06:15:00 CET (Europe/Amsterdam)" in answer.text
    assert "05:15:00 CET" not in answer.text
    for unchanged in (
        "Botbeslissing: 12 november 14:59 UTC",
        "Paper-uitvoering: 12 november 14:59 UTC",
        "FX-bron: 12 november 14:02 UTC",
        "Lesbevestiging: 13 november 09:07:57 UTC",
    ):
        assert unchanged in answer.text


def test_minimal_live_read_completes_repeated_owner_history_reads():
    prepared = _prepared(text=(
        "Exitreden: eerste koersdoel. De opgeslagen weekreflectie over 9–15 "
        "november 2026 registreert één trade. Weekreflectie gegenereerd: "
        "16 november 2026, 05:15 UTC (06:15 CET, Amsterdamse tijd)."
    ))
    prepared.response.tool_trace += prepared.response.tool_trace
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "AAPL Paper-trade als gesloten geregistreerd: 2026-11-12 16:02:00 CET" in answer.text
    assert "Geverifieerd opslagmoment week 2026-11-09 t/m 2026-11-15: 2026-11-16 06:15:00 CET" in answer.text


def test_minimal_live_read_scrubs_markdown_week_clock_after_repeated_reads():
    prepared = _prepared(text=(
        "Exitbeslissing: 12 november 14:59 UTC. "
        "Exitwisselkoers: 12 november 14:02 UTC. "
        "Bevestigde les: 13 november 09:07:57 UTC. "
        "**Opgeslagen weekreflectie gegenereerd:** "
        "16 november 2026, 05:15:00 Europe/Amsterdam."
    ))
    prepared.response.tool_trace += prepared.response.tool_trace
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "05:15:00 Europe/Amsterdam" not in answer.text
    assert "Opslagmoment van deze weekreflectie niet geverifieerd" in answer.text
    assert "AAPL Paper-trade als gesloten geregistreerd: 2026-11-12 16:02:00 CET" in answer.text
    assert "Geverifieerd opslagmoment week 2026-11-09 t/m 2026-11-15: 2026-11-16 06:15:00 CET" in answer.text
    for unchanged in (
        "Exitbeslissing: 12 november 14:59 UTC",
        "Exitwisselkoers: 12 november 14:02 UTC",
        "Bevestigde les: 13 november 09:07:57 UTC",
    ):
        assert unchanged in answer.text


def test_minimal_live_read_completes_missing_fx_source_moment_on_repeat():
    prepared = _prepared(text=(
        "Exitreden: eerste koersdoel. Botbeslissing: 12 november 14:59 UTC. "
        "Paper-uitstap: 12 november 15:02 UTC. Les: 13 november 09:07 UTC. "
        "Weekgeneratie: 16 november 05:15 UTC."
    ))
    prepared.response.tool_trace += prepared.response.tool_trace
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "Geverifieerd FX-bronmoment bij AAPL Paper-uitvoering: 2026-11-12 15:02:00 CET (Europe/Amsterdam)." in answer.text
    assert "Geverifieerd opslagmoment week 2026-11-09 t/m 2026-11-15: 2026-11-16 06:15:00 CET" in answer.text


def test_minimal_live_read_replaces_conflicting_model_fx_clock():
    for fx_claim in (
        "FX-bron: 12 november 14:03 UTC",
        "FX-factor 0.92 op 12 november 14:03 UTC",
        "De FX-koers had bronmoment 12 november 14:03 UTC",
        "Geverifieerd FX-bronmoment: 12 november 14:03 UTC",
        "Wisselkoersbron bij uitvoering: 12 november 14:03 UTC",
        "FX-bronmoment: 12 november 14:02 UTC (15:03 CET)",
        "FX-bronmoment: 12 november 14:02 UTC, 15:03 CET",
        "FX-bronmoment: 12 november 14:02 UTC, op 12 november 15:03 CET",
        "FX-bronmoment: 12 november 14:02 UTC en om 12 november 15:03 CET",
    ):
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=_prepared(text=(
                "Botbeslissing: 12 november 14:59 UTC. "
                f"{fx_claim}. De Paper-uitstap raakte het eerste koersdoel."
            )), user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert "14:03 UTC" not in answer.text
        assert "15:03 CET" not in answer.text
        assert "Botbeslissing: 12 november 14:59 UTC" in answer.text
        assert answer.text.count("Geverifieerd FX-bronmoment") == 1
        assert "2026-11-12 15:02:00 CET (Europe/Amsterdam)" in answer.text
        assert "FX-brontijd: zie de afzonderlijk geverifieerde bronregel" in answer.text
        assert "uit antwoordtekst niet geverifieerd" not in answer.text


def test_conflicting_fx_clock_inside_markdown_does_not_leave_closing_stars():
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION,
        prepared=_prepared(text=(
            "De Paper-uitstap raakte het eerste koersdoel. "
            "FX-bronmoment: **12 november 14:03 UTC**"
        )),
        user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "FX-brontijd: zie de afzonderlijk geverifieerde bronregel**" not in answer.text
    assert "FX-brontijd: zie de afzonderlijk geverifieerde bronregel" in answer.text


def test_historical_week_fx_moment_completion_is_idempotent():
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments

    prepared = _prepared(text="FX-bronmoment: 12 november 14:03 UTC.")
    evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
    first = complete_historical_week_exit_moments(
        prepared.response.text, evidence, question=LEGACY_QUESTION,
        user_time_zone="Europe/Amsterdam",
    )
    second = complete_historical_week_exit_moments(
        first, evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
    )
    assert second == first
    assert first.count("Geverifieerd FX-bronmoment") == 1
    assert "14:03 UTC" not in first


def test_historical_exit_completion_keeps_later_bot_clause_on_second_pass():
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments

    prepared = _prepared(text=(
        "FX-bronmoment: 12 november 14:03 UTC, "
        "botbeslissing 12 november 14:59 UTC."
    ))
    evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
    first = complete_historical_week_exit_moments(
        prepared.response.text, evidence, question=LEGACY_QUESTION,
        user_time_zone="Europe/Amsterdam",
    )
    second = complete_historical_week_exit_moments(
        first, evidence, question=LEGACY_QUESTION, user_time_zone="Europe/Amsterdam",
    )
    assert second == first
    assert "botbeslissing 12 november 14:59 UTC" in second
    assert "Geverifieerde AAPL Paper-exitbeslissing" in second


def test_historical_week_fx_scrub_preserves_next_labeled_source_after_comma():
    for claim, bot_moment in (
        ("FX-bronmoment: 12 november 14:02 UTC", "botbeslissing: 12 november 14:59 UTC"),
        ("Wisselkoersbron bij uitvoering: 12 november 14:03 UTC",
         "botbeslissing 12 november 14:59 UTC"),
        ("Wisselkoersbron bij uitvoering: 12 november 14:03 UTC",
         "bevestigde les 13 november 09:07:57 UTC"),
        ("Wisselkoersbron bij uitvoering: 12 november 14:03 UTC",
         "geregistreerde sluiting 12 november 15:00:30 UTC"),
    ):
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=_prepared(text=f"{claim}, {bot_moment}."),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert bot_moment in answer.text
        assert answer.text.count("Geverifieerd FX-bronmoment") == 1
        if "14:03" in claim:
            assert "14:03 UTC" not in answer.text
        else:
            assert claim in answer.text


def test_historical_week_fx_scrub_preserves_source_joined_with_en():
    for text, expected_bot in (
        ("Het FX-bronmoment was 12 november 14:03 UTC en de botbeslissing "
         "was 12 november 14:59 UTC.",
         "en de botbeslissing was 12 november 14:59 UTC"),
        ("Op 12 november was het FX-bronmoment 14:02 UTC en de botbeslissing "
         "om 14:59 UTC.", "en de botbeslissing om 14:59 UTC"),
    ):
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=_prepared(text=text),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert expected_bot in answer.text
        assert answer.text.count("Geverifieerd FX-bronmoment") == 1
        assert "14:03 UTC" not in answer.text


def test_historical_week_fx_scrub_preserves_labeled_source_in_parentheses():
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=_prepared(text=(
            "FX-bronmoment: 12 november 14:02 UTC "
            "(botbeslissing: 12 november 14:59 UTC)."
        )), user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "FX-bronmoment: 12 november 14:02 UTC" in answer.text
    assert "(botbeslissing: 12 november 14:59 UTC)" in answer.text
    assert answer.text.count("Geverifieerd FX-bronmoment") == 1


def test_minimal_live_read_does_not_invent_conflicting_fx_source_moment():
    prepared = _prepared(text=(
        "Exitreden: eerste koersdoel. "
        "Geverifieerd FX-bronmoment: 12 november 14:04 UTC."
    ))
    original = prepared.response.tool_trace[0]
    conflict = {**original, "result": {"results": [
        {**original["result"]["results"][0], "data": {
            **original["result"]["results"][0]["data"],
            "closed_trades": [{
                **original["result"]["results"][0]["data"]["closed_trades"][0],
                "paper_exit_evidence": {
                    "trigger": "first_target", "execution_fx_eur_per_unit": 0.92,
                    "execution_fx_observed_at": "2026-11-12T14:03:00+00:00",
                },
            }],
        }},
    ]}}
    prepared.response.tool_trace += (conflict,)
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "Geverifieerd FX-bronmoment" not in answer.text
    assert "14:04 UTC" not in answer.text
    assert "FX-brontijd: niet verifieerbaar uit opgeslagen bewijs" in answer.text


def test_minimal_live_read_neutralizes_fx_clock_when_source_missing():
    prepared = _prepared(text="FX-bron: 12 november 14:04 UTC.")
    prepared.response.tool_trace[0]["result"]["results"][0]["data"]["closed_trades"][0][
        "paper_exit_evidence"
    ] = None
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "14:04 UTC" not in answer.text
    assert "Geverifieerd FX-bronmoment" not in answer.text
    assert "FX-brontijd: niet verifieerbaar uit opgeslagen bewijs" in answer.text


def test_minimal_live_read_rejects_conflicting_repeated_history():
    prepared = _prepared(text="Exitreden: eerste doel. Weekreflectie opgeslagen: 05:15 UTC.")
    original = prepared.response.tool_trace[0]
    conflicting_week = {**original, "result": {"results": [
        {**original["result"]["results"][0], "data": {
            **original["result"]["results"][0]["data"],
            "weekly_reflection": {
                **original["result"]["results"][0]["data"]["weekly_reflection"],
                "generated_at": "2026-11-16T06:15:00+00:00",
            },
        }},
    ]}}
    prepared.response.tool_trace += (conflicting_week,)
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "als gesloten geregistreerd" not in answer.text
    assert "Geverifieerd opslagmoment" not in answer.text

    for identity_change in ({"symbol": "MSFT"}, {"environment": "live"}):
        conflicting_identity = _prepared(
            text="Exitreden: eerste doel. Weekreflectie opgeslagen: 05:15 UTC.",
        )
        original = conflicting_identity.response.tool_trace[0]
        changed = {**original, "result": {"results": [
            {**original["result"]["results"][0], "data": {
                **original["result"]["results"][0]["data"],
                "closed_trades": [{
                    **original["result"]["results"][0]["data"]["closed_trades"][0],
                    **identity_change,
                }],
            }},
        ]}}
        conflicting_identity.response.tool_trace += (changed,)
        answer = _minimal_read_answer(
            message=LEGACY_QUESTION, prepared=conflicting_identity,
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert "als gesloten geregistreerd" not in answer.text

    conflicting_outside_week = _prepared(text="Exitreden: eerste doel. Weekreflectie opgeslagen: 05:15 UTC.")
    original = conflicting_outside_week.response.tool_trace[0]
    outside = {**original, "result": {"results": [
        {**original["result"]["results"][0], "data": {
            **original["result"]["results"][0]["data"],
            "closed_trades": [{
                **original["result"]["results"][0]["data"]["closed_trades"][0],
                "exit_at": "2026-11-05T15:02:00+00:00",
            }],
        }},
    ]}}
    conflicting_outside_week.response.tool_trace += (outside,)
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=conflicting_outside_week,
        user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "als gesloten geregistreerd" not in answer.text

    separate_old_dossier = _prepared(text="Exitreden: eerste doel. Weekreflectie opgeslagen: 05:15 UTC.")
    old_trade = {**original, "result": {"results": [
        {**original["result"]["results"][0], "data": {
            **original["result"]["results"][0]["data"],
            "closed_trades": [{
                **original["result"]["results"][0]["data"]["closed_trades"][0],
                "review_id": 1999, "exit_at": "2026-11-05T15:02:00+00:00",
            }],
        }},
    ]}}
    separate_old_dossier.response.tool_trace += (old_trade,)
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=separate_old_dossier,
        user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "als gesloten geregistreerd" in answer.text
    assert "Geverifieerd opslagmoment" in answer.text

    conflicting_trade = _prepared(text="Exitreden: eerste doel. Weekreflectie opgeslagen: 05:15 UTC.")
    original = conflicting_trade.response.tool_trace[0]
    other_trade = {**original, "result": {"results": [
        {**original["result"]["results"][0], "data": {
            **original["result"]["results"][0]["data"],
            "closed_trades": [{
                **original["result"]["results"][0]["data"]["closed_trades"][0],
                "exit_at": "2026-11-12T15:10:00+00:00",
            }],
        }},
    ]}}
    conflicting_trade.response.tool_trace += (other_trade,)
    answer = _minimal_read_answer(
        message=LEGACY_QUESTION, prepared=conflicting_trade,
        user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "als gesloten geregistreerd" not in answer.text
