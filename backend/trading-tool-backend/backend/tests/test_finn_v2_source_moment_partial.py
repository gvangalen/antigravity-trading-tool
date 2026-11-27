from types import SimpleNamespace

from backend.services.finn_v2_run_service import _minimal_read_answer
from backend.services.finn_v2_source_moment_claims import current_source_moments_supported
from backend.services.finn_v2_source_moment_partial import (
    is_mixed_bot_position_question, render_source_moment_partial,
)
from backend.services.finn_v2_turn_contract import build_turn_contract, turn_contract_gap


QUESTION = (
    "Mijn BTC-bot 129 wacht wegens setupmismatch; de handmatige Paper-preview "
    "blokkeert bij 35 onder 61. Het dagrapport toont BTC/EUR 36,7 en "
    "BTC/USDT 40. Moet ik nu BTC kopen? Leg het verschil tussen rapport, "
    "paaranalyse en botplan uit, en benoem mijn open ETH-positie uit de "
    "scorevrije QA-test. Geef een veilige volgende stap."
)


def _cross_source_contract():
    return {
        "question": QUESTION, "answer_type": "compare", "requested_fields": ["position_size"],
        "targets": [
            {"setup_id": 12, "name": "BTC herstelplan", "asset_alias_unique": True,
             "evidence": {"symbol": "BTC"}, "strategy": {}},
            {"setup_id": 13, "name": "ETH weekplan", "asset_alias_unique": True,
             "evidence": {"symbol": "ETH"}, "strategy": {}},
        ],
    }


def _evidence():
    return (
        {"scope": "read_bot_status", "status": "completed", "asset": "BTC", "data": {
            "bot_id": 129, "operational_status": "paused", "is_live": False,
            "read_at": "2026-11-26T16:30:00+00:00",
        }},
        {"scope": "read_review_history", "status": "completed", "asset": "BTC", "data": {
            "latest_bot_decisions": [{
                "bot_id": 129, "symbol": "BTC", "pair": "BTC/EUR", "action": "hold",
                "is_live": False,
                "decision_at": "2026-11-26T16:25:00+00:00",
            }],
        }},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_type": "daily_reports",
            "generated_at": "2026-11-26T05:00:00+00:00",
            "score_source_snapshot": {"assets": [
                {"pair": "BTC/EUR", "score_status": "available", "benchmark_score": 36.7},
                {"pair": "BTC/USDT", "score_status": "available", "benchmark_score": 40},
            ]},
        }},
        {"scope": "read_linked_bot", "status": "completed", "asset": "BTC", "data": {
            "bot_id": 129, "symbol": "BTC", "pair": "BTC/EUR",
            "setup_id": 12, "is_live": False,
        }},
        {"scope": "read_active_setup", "status": "completed", "asset": "BTC", "data": {
            "setup_id": 12, "symbol": "BTC", "min_benchmark_score": 61,
            "max_benchmark_score": 75,
        }},
        {"scope": "read_asset_scores", "status": "completed", "asset": "BTC", "data": {
            "pair": "BTC/EUR", "market_id": 1, "source_status": "available", "benchmark_score": 35.0,
        }},
        {"scope": "read_asset_scores", "status": "completed", "asset": "BTC", "data": {
            "pair": "BTC/USDT", "market_id": 2, "source_status": "unverified_scores", "benchmark_score": 40.0,
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "read_at": "2026-11-26T16:31:00+00:00",
            "bots": [{"bot_id": 301, "symbol": "ETH", "is_live": False,
                      "position_qty": 0.00644603}],
        }},
    )


def test_multi_asset_wrong_clock_recovers_only_owner_read_facts():
    evidence = _evidence()
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Bot #129 is voor het laatst beoordeeld op 26 november 2026 om 10:00 CET.",
            tool_trace=({"name": "get_decision_history", "result": {
                "results": list(evidence),
            }},),
            uses_previous_response=False,
            turn_contract=_cross_source_contract(),
        ),
    )

    answer = _minimal_read_answer(message=QUESTION, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "10:00 CET" not in answer.text
    assert "Bot #129" in answer.text
    assert "wachten" in answer.text
    assert "dagrapport" in answer.text
    assert "rapportmomentopname staat voor BTC/EUR benchmarkscore 36,7/100" in answer.text
    assert "rapportmomentopname staat voor BTC/USDT benchmarkscore 40/100" in answer.text
    assert "handmatige preview kan een andere setup" in answer.text
    assert "BTC/EUR" in answer.text and "BTC/USDT" in answer.text
    assert "BTC/EUR heeft benchmarkscore 35/100" in answer.text
    assert "BTC/USDT heeft benchmarkscore 40/100" not in answer.text
    assert "0,00644603 ETH" in answer.text
    assert "geen nieuwe koop onderbouwen" in answer.text
    assert answer.text.endswith("Wil je dat ik de handmatige preview en de bijbehorende setup apart controleer?")
    assert turn_contract_gap(_cross_source_contract(), answer.text) == "comparison_targets_missing"


def test_cross_source_contract_gap_recovers_owner_read_partial_answer():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Vermeng geen "
        "verschillende handelspaarbronnen. Lees alleen."
    )
    evidence = _evidence()
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Ik kan hiermee geen nieuwe koop onderbouwen.",
            tool_trace=({"name": "get_decision_history", "result": {
                "results": list(evidence),
            }},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "Bot #129" in answer.text
    assert "gekoppelde plan vereist een benchmarkscore tussen 61 en 75" in answer.text
    assert "0,00644603 ETH" in answer.text
    assert "BTC/EUR" in answer.text
    assert "rapportmomentopname" not in answer.text
    assert "De gelezen paaranalyse" not in answer.text
    assert "Ik heb je vraag nog niet volledig beantwoord" not in answer.text


def test_contract_recovery_does_not_bind_btc_eur_to_btc_usdt_bot():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Vermeng geen "
        "verschillende handelspaarbronnen. Lees alleen."
    )
    evidence = list(_evidence())
    linked = next(item for item in evidence if item["scope"] == "read_linked_bot")
    linked["data"] = {**linked["data"], "pair": "BTC/USDT"}
    portfolio = next(item for item in evidence if item["scope"] == "read_portfolio")
    portfolio["data"]["bots"].append({
        "bot_id": 129, "symbol": "BTC", "is_live": False,
        "operational_status": "active",
    })
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Ik kan hiermee geen nieuwe koop onderbouwen.",
            tool_trace=({"name": "get_decision_history", "result": {
                "results": evidence,
            }},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "BTC/EUR is het genoemde analysepaar" in answer.text
    assert "benchmarkscore 35/100" not in answer.text
    assert "0,00644603 ETH" in answer.text
    assert "gekoppelde plan vereist" not in answer.text
    assert "Bot #129 heeft volgens de gelezen botstatus" not in answer.text
    assert "bot #129 op actief" not in answer.text
    assert answer.text.endswith(
        "Bot #129 is gelezen voor BTC/USDT; wil je de voorwaarden voor dat handelspaar apart laten controleren?"
    )


def test_mixed_bot_position_portfolio_read_answers_known_facts_without_pair_claim():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Vermeng geen "
        "verschillende handelspaarbronnen. Lees alleen."
    )
    portfolio = {"scope": "read_portfolio", "status": "completed", "data": {
        "read_at": "2026-11-26T16:31:00+00:00",
        "bots": [
            {"bot_id": 129, "symbol": "BTC", "is_live": False,
             "operational_status": "active", "setup_id": 12},
            {"bot_id": 301, "symbol": "ETH", "is_live": False,
             "position_qty": 0.00644603},
        ],
    }}
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Ik kan hiermee geen nieuwe koop onderbouwen.",
            tool_trace=({"name": "get_portfolio_and_exposure", "result": {
                "results": [portfolio],
            }},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "In de gelezen Paper-portefeuille staat bot #129 op actief" in answer.text
    assert "0,00644603 ETH" in answer.text
    assert "gekoppelde plan vereist" not in answer.text
    assert "BTC/EUR heeft benchmarkscore" not in answer.text
    assert answer.text.endswith("Wil je dat ik de koppeling en het eigen handelspaar van bot #129 opnieuw controleer?")


def test_mixed_bot_position_reports_verified_zero_without_unasked_report_score():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Vermeng geen "
        "verschillende handelspaarbronnen. Lees alleen."
    )
    evidence = [
        {"scope": "read_portfolio", "status": "completed", "data": {
            "bots": [
                {"bot_id": 129, "symbol": "BTC", "is_live": False,
                 "operational_status": "active"},
                {"bot_id": 301, "symbol": "ETH", "is_live": False,
                 "position_qty": 0},
            ],
        }},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_type": "daily_reports", "score_source_snapshot": {"assets": [
                {"pair": "BTC/EUR", "score_status": "available", "benchmark_score": 36.7},
            ]},
        }},
    ]
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Ik kan hiermee geen nieuwe koop onderbouwen.",
            tool_trace=({"name": "get_portfolio_and_exposure", "result": {"results": evidence}},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )
    answer = _minimal_read_answer(message=question, prepared=prepared)
    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "bot #129 op actief" in answer.text
    assert "bot #301 geen open ETH-positie (0 ETH)" in answer.text
    assert "de ETH-positie niet eenduidig" not in answer.text
    assert "36,7" not in answer.text
    assert "rapportmomentopname" not in answer.text


def test_mixed_bot_position_overrides_fluid_model_pair_mix_and_uses_zero_read():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Vermeng geen "
        "verschillende handelspaarbronnen. Lees alleen."
    )
    evidence = list(_evidence())
    linked = next(item for item in evidence if item["scope"] == "read_linked_bot")
    linked["data"] = {**linked["data"], "pair": "BTC/USDT"}
    portfolio = next(item for item in evidence if item["scope"] == "read_portfolio")
    portfolio["data"] = {**portfolio["data"], "bots": [
        {"bot_id": 129, "symbol": "BTC", "is_live": False,
         "operational_status": "active"},
        {"bot_id": 301, "symbol": "ETH", "is_live": False,
         "position_qty": 0},
    ]}
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text=("Voor BTC/EUR ligt de score 33,3 onder de 61–75-band van bot 129. "
                  "De ETH-uitlezing is niet specifiek genoeg om de positie te bevestigen."),
            tool_trace=({"name": "get_portfolio_and_exposure", "result": {
                "results": evidence,
            }},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    assert is_mixed_bot_position_question(question)
    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "bot #301 geen open ETH-positie (0 ETH)" in answer.text
    assert "BTC/EUR is het genoemde analysepaar" in answer.text
    assert "BTC/USDT" in answer.text
    assert "33,3" not in answer.text
    assert "61 en 75" not in answer.text
    assert "niet specifiek genoeg" not in answer.text


def test_mixed_bot_position_intent_excludes_score_only_question():
    assert not is_mixed_bot_position_question(
        "Vergelijk de actuele scores van BTC/EUR en ETH/EUR. Lees alleen."
    )


def test_mixed_bot_position_failed_recovery_never_returns_model_pair_mix():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Lees alleen."
    )
    model_text = "BTC/EUR 33,3 ligt onder de 61–75-band van mijn BTC/USDT-bot."
    prepared = SimpleNamespace(
        locale="en", previous_response=None,
        response=SimpleNamespace(
            text=model_text, tool_trace=(), uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "unavailable"
    assert answer.reason == "mixed_bot_position_source_incomplete"
    assert "check the bot and portfolio separately" in answer.text
    assert "33,3" not in answer.text
    assert "61–75" not in answer.text


def test_mixed_bot_position_without_completed_reads_is_not_marked_answered():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Lees alleen."
    )
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="BTC/EUR 33,3 ligt onder de botband 61–75.",
            tool_trace=(), uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "unavailable"
    assert answer.reason == "mixed_bot_position_source_incomplete"
    assert "bot en Paper-portefeuille afzonderlijk" in answer.text
    assert "Welk asset" not in answer.text
    assert "33,3" not in answer.text


def test_mixed_bot_position_two_pairs_without_reads_is_not_marked_answered():
    question = (
        "Vergelijk BTC/EUR en BTC/USDT met mijn open ETH-positie. "
        "Welke planvoorwaarden horen bij BTC-bot 129? Lees alleen."
    )
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="BTC/EUR 33,3 ligt onder de BTC/USDT-botband 61–75.",
            tool_trace=(), uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    assert render_source_moment_partial(
        question=question, evidence=(), require_facts=True,
    ) is None
    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "unavailable"
    assert answer.reason == "mixed_bot_position_source_incomplete"
    assert "Welk van de genoemde handelsparen" not in answer.text
    assert "33,3" not in answer.text


def test_mixed_bot_position_invalid_score_read_does_not_count_as_fact():
    question = (
        "Vergelijk de scores van BTC/EUR en BTC/USDT met mijn open ETH-positie "
        "en BTC-bot 129. Lees alleen."
    )
    evidence = ({"scope": "read_asset_scores", "status": "completed", "data": {
        "pair": "BTC/EUR", "market_id": 1, "source_status": "unverified_scores",
        "benchmark_score": 33.3,
    }},)

    assert render_source_moment_partial(
        question=question, evidence=evidence, require_facts=True,
    ) is None


def test_mixed_bot_position_does_not_infer_zero_from_missing_quantity():
    question = "Vergelijk BTC/EUR met mijn open ETH-positie en BTC-bot 129. Lees alleen."
    evidence = ({"scope": "read_portfolio", "status": "completed", "data": {
        "bots": [
            {"bot_id": 129, "symbol": "BTC", "is_live": False,
             "operational_status": "active"},
            {"bot_id": 301, "symbol": "ETH", "is_live": False,
             "position_qty": None},
        ],
    }},)
    answer = render_source_moment_partial(question=question, evidence=evidence)
    assert answer is not None
    assert "geen open ETH-positie" not in answer
    assert "de ETH-positie" in answer


def test_one_zero_eth_bot_does_not_confirm_all_eth_positions():
    question = "Vergelijk BTC/EUR met mijn open ETH-positie en BTC-bot 129. Lees alleen."
    evidence = ({"scope": "read_portfolio", "status": "completed", "data": {
        "bots": [
            {"bot_id": 129, "symbol": "BTC", "is_live": False,
             "operational_status": "active"},
            {"bot_id": 301, "symbol": "ETH", "is_live": False,
             "position_qty": 0},
            {"bot_id": 302, "symbol": "ETH", "is_live": False,
             "position_qty": None},
        ],
    }},)
    answer = render_source_moment_partial(question=question, evidence=evidence)
    assert answer is not None
    assert "bot #301 geen open ETH-positie (0 ETH)" in answer
    assert "bot #302 geen open ETH-positie" not in answer
    assert "de ETH-positie" in answer.split("Ik kon", 1)[-1]


def test_score_only_question_does_not_claim_open_zero_position():
    question = "Vergelijk de actuele scores van BTC/EUR en ETH/EUR. Lees alleen."
    evidence = (
        {"scope": "read_asset_scores", "status": "completed", "data": {
            "pair": "BTC/EUR", "market_id": 1,
            "source_status": "available", "benchmark_score": 33.3,
        }},
        {"scope": "read_asset_scores", "status": "completed", "data": {
            "pair": "ETH/EUR", "market_id": 2,
            "source_status": "available", "benchmark_score": 34.4,
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "bots": [{"bot_id": 301, "symbol": "ETH", "is_live": False,
                      "position_qty": 0}],
        }},
    )
    answer = render_source_moment_partial(question=question, evidence=evidence)
    assert answer is not None
    assert "BTC/EUR heeft benchmarkscore 33,3/100" in answer
    assert "ETH/EUR heeft benchmarkscore 34,4/100" in answer
    assert "positie" not in answer


def test_conflicting_bot_reads_with_same_other_pair_do_not_restore_portfolio_status():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Lees alleen."
    )
    evidence = list(_evidence())
    linked = next(item for item in evidence if item["scope"] == "read_linked_bot")
    linked["data"] = {**linked["data"], "pair": "BTC/USDT", "is_active": True}
    evidence.append({**linked, "data": {**linked["data"], "is_active": False}})
    portfolio = next(item for item in evidence if item["scope"] == "read_portfolio")
    portfolio["data"]["bots"].append({
        "bot_id": 129, "symbol": "BTC", "is_live": False,
        "operational_status": "active",
    })
    answer = render_source_moment_partial(question=question, evidence=tuple(evidence))
    assert answer is not None
    assert "bot #129 op actief" not in answer
    assert "Bot #129 heeft volgens de gelezen botstatus" not in answer


def test_mixed_bot_position_does_not_treat_bot_status_as_eth_position():
    question = (
        "Vergelijk BTC/EUR met mijn open ETH-positie. Wat is de status van mijn "
        "BTC-bot 129 en welke planvoorwaarden horen bij die bot? Lees alleen."
    )
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Ik kan hiermee geen nieuwe koop onderbouwen.",
            tool_trace=({"name": "get_portfolio_and_exposure", "result": {"results": [{
                "scope": "read_portfolio", "status": "completed", "data": {
                    "bots": [{"bot_id": 129, "symbol": "BTC", "is_live": False,
                              "operational_status": "active"}],
                },
            }]}},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )
    answer = _minimal_read_answer(message=question, prepared=prepared)
    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "bot #129 op actief" in answer.text
    assert "de ETH-positie" in answer.text
    assert "open positie van" not in answer.text


def test_saved_setup_comparison_does_not_use_cross_source_contract_recovery():
    question = "Vergelijk mijn BTC-setup en ETH-setup."
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Ik kan hiermee geen nieuwe koop onderbouwen.",
            tool_trace=({"name": "get_decision_history", "result": {
                "results": list(_evidence()),
            }},),
            uses_previous_response=False,
            turn_contract={**_cross_source_contract(), "question": question},
        ),
    )

    answer = _minimal_read_answer(message=question, prepared=prepared)

    assert answer.status == "unavailable"
    assert answer.reason == "turn_contract_mismatch"
    assert answer.rejection_details["gap"] == "comparison_targets_missing"


def test_saved_report_bot_decision_preserves_clockless_status_and_plan_facts():
    evidence = [item for item in _evidence() if item["scope"] != "read_review_history"]
    report = next(item for item in evidence if item["scope"] == "read_latest_report")
    report["data"]["score_source_snapshot"]["report_v2"] = {"automation": {"bots": [{
        "bot_id": 129, "symbol": "BTC", "latest_decision": {
            "at": "2026-11-26T05:00:00+00:00",
        },
    }]}}
    prepared = SimpleNamespace(
        locale="nl", previous_response=None,
        response=SimpleNamespace(
            text="Bot #129 is voor het laatst beoordeeld op 26 november 2026 om 10:00 CET.",
            tool_trace=({"name": "get_decision_history", "result": {
                "results": evidence,
            }},),
            uses_previous_response=False,
            turn_contract=None,
        ),
    )

    answer = _minimal_read_answer(message=QUESTION, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "rapportmomentopname staat voor BTC/EUR benchmarkscore 36,7/100" in answer.text
    assert "BTC/EUR heeft benchmarkscore 35/100" in answer.text
    assert "0,00644603 ETH" in answer.text
    assert "Bot #129 heeft volgens de gelezen botstatus de status gepauzeerd" in answer.text
    assert "Het gelezen dagrapport is een opgeslagen momentopname" in answer.text
    assert "gekoppelde plan vereist een benchmarkscore tussen 61 en 75" in answer.text
    assert "geen nieuwe koop onderbouwen" in answer.text
    assert "handmatige preview en de bijbehorende setup apart controleer" in answer.text
    assert "10:00 CET" not in answer.text
    assert not current_source_moments_supported(
        "De laatste beslissing voor bot #129 is wachten.", tuple(evidence),
        question=QUESTION,
    )
    assert not current_source_moments_supported(
        "Het laatste botsignaal voor bot #129 is positief.", tuple(evidence),
        question=QUESTION,
    )


def test_typed_recovery_still_requires_targets_for_saved_setup_comparison():
    contract = {**_cross_source_contract(), "question": "Vergelijk beide setups."}

    assert turn_contract_gap(
        contract, "Het BTC-plan verschilt van de ETH-positie.", typed_recovery=True,
    ) == "comparison_targets_missing"
    inherited = build_turn_contract(
        message="Vergelijk die twee", tool_trace=(),
        previous_contract=_cross_source_contract(),
    )
    assert inherited["comparison_targets_inherited"] is True
    assert turn_contract_gap(
        inherited, "Het BTC-plan verschilt van de ETH-positie.", typed_recovery=True,
    ) == "comparison_targets_missing"
    named_by_asset = {
        **_cross_source_contract(), "question": "Vergelijk mijn BTC-setup en ETH-setup.",
    }
    assert turn_contract_gap(
        named_by_asset, "Het BTC-plan is gelezen.", typed_recovery=True,
    ) == "comparison_targets_missing"
    reread_pair = build_turn_contract(
        message="Vergelijk de vorige configuraties voor BTC/EUR en ETH/EUR op basis van het rapport",
        tool_trace=({"result": {"results": [
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 12, "name": "BTC herstelplan", "symbol": "BTC",
            }},
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 13, "name": "ETH weekplan", "symbol": "ETH",
            }},
        ]}},),
        previous_contract=_cross_source_contract(),
    )
    assert reread_pair["comparison_targets_inherited"] is True
    assert turn_contract_gap(
        reread_pair, "Het BTC-plan is gelezen.", typed_recovery=True,
    ) == "comparison_targets_missing"


def test_typed_recovery_score_comparison_ignores_incidental_saved_setups():
    contract = {
        **_cross_source_contract(),
        "question": "Vergelijk de scores van BTC/EUR en ETH/EUR.",
    }
    answer = "BTC/EUR heeft score 33,3/100; ETH/EUR heeft score 33,3/100."

    assert turn_contract_gap(contract, answer) == "comparison_targets_missing"
    assert turn_contract_gap(contract, answer, typed_recovery=True) is None
    setup_referent = {
        **contract,
        "question": "Vergelijk voor BTC en ETH de scores van die twee",
    }
    assert turn_contract_gap(
        setup_referent, answer, typed_recovery=True,
    ) == "comparison_targets_missing"


def test_typed_recovery_score_comparison_after_saved_setup_pair():
    question = "Vergelijk per paar de scores van BTC/EUR en ETH/EUR."
    contract = build_turn_contract(
        message=question,
        tool_trace=({"result": {"results": [
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 12, "name": "BTC herstelplan", "symbol": "BTC",
            }},
            {"scope": "read_active_setup", "status": "completed", "data": {
                "setup_id": 13, "name": "ETH weekplan", "symbol": "ETH",
            }},
        ]}},),
        previous_contract=_cross_source_contract(),
    )
    answer = "BTC/EUR heeft score 33,3/100; ETH/EUR heeft score 33,3/100."

    assert contract["comparison_targets_inherited"] is True
    assert turn_contract_gap(contract, answer) == "comparison_targets_missing"
    assert turn_contract_gap(contract, answer, typed_recovery=True) is None
    setup_referent = {
        **contract,
        "question": "Vergelijk voor BTC en ETH de scores van die twee",
    }
    assert turn_contract_gap(
        setup_referent, answer, typed_recovery=True,
    ) == "comparison_targets_missing"


def test_partial_answer_does_not_repeat_unread_eth_position_or_bot_status():
    evidence = (_evidence()[2],)

    answer = render_source_moment_partial(question=QUESTION, evidence=evidence)

    assert answer is not None
    assert "dagrapport" in answer
    assert "open positie van" not in answer
    assert "gepauzeerd" not in answer
    assert "0,00644603" not in answer
    assert "setupmismatch" not in answer


def test_partial_answer_requires_completed_source_and_multi_source_question():
    assert render_source_moment_partial(
        question=QUESTION, evidence=(),
    ) == "Welk van de genoemde handelsparen hoort bij bot #129?"
    assert render_source_moment_partial(
        question="Wat is de huidige botstatus van BTC?", evidence=_evidence(),
    ) is None


def test_conflicting_pair_scores_and_portfolio_positions_are_omitted():
    evidence = _evidence() + (
        {"scope": "read_asset_scores", "status": "completed", "asset": "BTC", "data": {
            "pair": "BTC/EUR", "market_id": 1, "source_status": "available", "benchmark_score": 36.7,
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "bots": [{"bot_id": 301, "symbol": "ETH", "is_live": False,
                      "position_qty": 0.007}],
        }},
    )

    answer = render_source_moment_partial(question=QUESTION, evidence=evidence)

    assert answer is not None
    assert "BTC/EUR heeft benchmarkscore" not in answer
    assert "0,00644603 ETH" not in answer
    assert "0,007 ETH" not in answer


def test_bot_status_and_decision_require_matching_asset_and_paper_mode():
    evidence = (
        {"scope": "read_bot_status", "status": "completed", "asset": "ETH", "data": {
            "bot_id": 129, "operational_status": "paused", "is_live": False,
        }},
        {"scope": "read_review_history", "status": "completed", "asset": "BTC", "data": {
            "latest_bot_decisions": [{"bot_id": 129, "symbol": "BTC", "action": "hold",
                                      "is_live": True}],
        }},
    )

    answer = render_source_moment_partial(question=QUESTION, evidence=evidence)

    assert answer is not None
    assert "status gepauzeerd" not in answer
    assert "beslissing voor bot #129" not in answer


def test_partial_explains_bound_setup_threshold_and_known_block_reason():
    evidence = list(_evidence())
    evidence[1]["data"]["latest_bot_decisions"][0]["safety_reason"] = (
        "Opgeslagen setupvoorwaarden passen niet bij de actuele scores."
    )

    answer = render_source_moment_partial(question=QUESTION, evidence=tuple(evidence))

    assert "opgeslagen botreden" in answer and "opgeslagen setupvoorwaarden" in answer
    assert "bot #129 gekoppelde plan vereist een benchmarkscore tussen 61 en 75" in answer
    assert "rapportscore is geen koopopdracht" in answer


def test_unrelated_weekly_report_and_unlinked_eth_setup_are_not_claimed():
    evidence = (
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_type": "weekly_reports", "symbol": "ETH",
        }},
        {"scope": "read_active_setup", "status": "completed", "asset": "ETH", "data": {
            "setup_id": 99, "symbol": "ETH", "min_benchmark_score": 61,
            "max_benchmark_score": 75,
        }},
    )

    answer = render_source_moment_partial(question=QUESTION, evidence=evidence)

    assert "gelezen dagrapport" not in answer
    assert "gekoppelde plan" not in answer
    assert "de bot en zijn plan, de scores, de Paper-positie" in answer


def test_unrelated_read_yields_specific_clarification_not_fake_source_answer():
    answer = render_source_moment_partial(question=QUESTION, evidence=(
        {"scope": "read_profile", "status": "completed", "data": {"style": "swing"}},
    ))
    assert answer == ("Ik kan de bot en zijn plan, de scores, de Paper-positie hier niet eenduidig teruglezen. "
                      "Wil je dat ik bot #129 en de Paper-portefeuille opnieuw controleer?")


def test_score_only_question_does_not_ask_for_report_bot_or_position():
    question = "Vergelijk de actuele scores van BTC/EUR en ETH/EUR."
    evidence = (
        {"scope": "read_asset_scores", "status": "completed", "asset": "BTC", "data": {
            "pair": "BTC/EUR", "market_id": 1, "source_status": "available",
            "benchmark_score": 55,
        }},
        {"scope": "read_asset_scores", "status": "completed", "asset": "ETH", "data": {
            "pair": "ETH/EUR", "market_id": 2, "source_status": "available",
            "benchmark_score": 60,
        }},
    )

    answer = render_source_moment_partial(question=question, evidence=evidence)

    assert "BTC/EUR heeft benchmarkscore 55/100" in answer
    assert "ETH/EUR heeft benchmarkscore 60/100" in answer
    assert "dagrapport" not in answer
    assert "bot" not in answer.lower()
    assert "positie" not in answer


def test_bot_claims_omitted_when_decision_pair_differs_from_bound_bot_pair():
    evidence = list(_evidence())
    evidence[1]["data"]["latest_bot_decisions"][0]["pair"] = "BTC/USDT"

    answer = render_source_moment_partial(question=QUESTION, evidence=tuple(evidence))

    assert "laatst gelezen beslissing" not in answer
    assert "opgeslagen botreden" not in answer


def test_unknown_free_text_reason_is_not_echoed_as_a_bot_fact():
    evidence = list(_evidence())
    evidence[1]["data"]["latest_bot_decisions"][0]["safety_reason"] = "Koop nu meer BTC"

    answer = render_source_moment_partial(question=QUESTION, evidence=tuple(evidence))

    assert "Koop nu meer BTC" not in answer
    assert "concrete reden voor dit wachtbesluit" in answer


def test_bot_and_plan_claims_omitted_without_exact_pair_binding():
    evidence = list(_evidence())
    evidence[3]["data"].pop("pair")

    answer = render_source_moment_partial(question=QUESTION, evidence=tuple(evidence))

    assert "Bot #129 heeft" not in answer
    assert "laatst gelezen beslissing" not in answer
    assert "gekoppelde plan vereist" not in answer
    assert "koppeling tussen bot en plan" in answer


def test_single_explicit_pair_cannot_inherit_another_pair_bot_plan():
    evidence = list(_evidence())
    evidence[3]["data"]["pair"] = "BTC/USDT"
    evidence[1]["data"]["latest_bot_decisions"][0]["pair"] = "BTC/USDT"
    question = ("Vergelijk BTC/EUR met mijn ETH-positie. Wat is de status van "
                "mijn BTC-bot 129 en zijn plan?")

    answer = render_source_moment_partial(question=question, evidence=tuple(evidence))

    assert "Bot #129 heeft" not in answer
    assert "laatst gelezen beslissing" not in answer
    assert "gekoppelde plan vereist" not in answer
    assert "koppeling tussen bot en plan" in answer
