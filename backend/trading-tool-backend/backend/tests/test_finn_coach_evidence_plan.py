from backend.services.finn_v2_coach_evidence_plan import coach_evidence_plan
from backend.services.finn_v2_turn_contract import turn_contract_gap
from backend.services.finn_v2_coach_source_fallback import (
    coach_source_coverage_gap, render_coach_source_fallback,
)
from backend.services.finn_v2_run_service import _minimal_read_answer
from types import SimpleNamespace


def test_named_asset_coach_question_plans_each_requested_source():
    question = ("Beoordeel mijn AAPL-setup, score, botreden, rapport en koers. "
                "Wat doe ik bij de beursopening? Bespreek alleen.")
    plan = coach_evidence_plan(question, named_asset_count=1, read_only=True)
    assert plan is not None
    assert set(plan.read_tools) == {
        "read_active_setup", "read_linked_strategy", "read_asset_scores",
        "read_bot_status", "read_review_history", "read_latest_report",
        "read_market_snapshot", "read_portfolio",
    }
    assert plan.decision_required
    assert plan.next_step_required
    assert coach_evidence_plan(question, named_asset_count=2, read_only=True) is None
    assert coach_evidence_plan(question, named_asset_count=1, read_only=False) is None


def test_bot_decision_plus_score_reads_bot_identity_even_without_cash_question():
    question = "Waarom is mijn BTC Paper-bot geblokkeerd en wat zegt de actuele benchmarkscore? Lees alleen."
    plan = coach_evidence_plan(question, named_asset_count=1, read_only=True)
    assert plan is not None
    assert plan.topics == ("score", "bot")
    assert "read_portfolio" in plan.read_tools


def test_bot_setup_question_uses_bot_parent_not_newer_same_asset_setup():
    question = (
        "Welke opgeslagen setup en strategie zijn daadwerkelijk aan mijn actieve "
        "BTC Paper-bot gekoppeld? Controleer de relatie opnieuw. Lees alleen."
    )
    plan = coach_evidence_plan(question, named_asset_count=1, read_only=True)
    assert plan is not None
    assert "read_portfolio" in plan.read_tools
    evidence = (
        {"scope": "read_active_setup", "status": "completed", "data": {
            "id": 20, "symbol": "BTC", "name": "Nieuwere Smart DCA"}},
        {"scope": "read_linked_strategy", "status": "completed", "data": {
            "id": 30, "symbol": "BTC", "name": "Nieuwere Smart DCA Strategy"}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "bots": [{"bot_id": 56, "name": "Long term DCA Bot", "symbol": "BTC",
                      "is_active": True,
                      "is_live": False, "setup_id": 10, "setup_name": "Long term DCA BTC",
                      "strategy_id": 15, "strategy_name": "Long term DCA Strategy"}]}}
    )
    answer = render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=evidence, question=question,
    )
    assert answer is not None
    assert "Long term DCA BTC" in answer
    assert "Long term DCA Strategy" in answer
    assert "Nieuwere Smart DCA" not in answer
    assert coach_source_coverage_gap(
        asset="BTC", topics=plan.topics, evidence=evidence, question=question,
        answer="De bot is gekoppeld aan Nieuwere Smart DCA en Nieuwere Smart DCA Strategy.",
    ) == "bot_plan_lineage_missing"
    for unsupported in (
        "De bot is gekoppeld aan Fantasie Plan en Fantasie Strategy.",
        "De bot is gekoppeld aan setup 20 en strategie 30.",
    ):
        assert coach_source_coverage_gap(
            asset="BTC", topics=plan.topics, evidence=evidence, question=question,
            answer=unsupported,
        ) in {"bot_plan_lineage_missing", "bot_plan_lineage_mismatch"}
    other_wording = question.replace("zijn daadwerkelijk aan", "horen bij").replace(" gekoppeld?", "?")
    assert "read_portfolio" in coach_evidence_plan(
        other_wording, named_asset_count=1, read_only=True,
    ).read_tools
    assert "Long term DCA BTC" in render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=evidence, question=other_wording,
    )
    for variant in (
        "Welke setup en strategie gebruikt mijn actieve BTC Paper-bot? Lees alleen.",
        "Op welke setup en strategie draait mijn actieve BTC Paper-bot? Lees alleen.",
    ):
        variant_plan = coach_evidence_plan(variant, named_asset_count=1, read_only=True)
        assert variant_plan is not None and "read_portfolio" in variant_plan.read_tools
        variant_prepared = SimpleNamespace(response=SimpleNamespace(
            text="De bot gebruikt Nieuwere Smart DCA en Nieuwere Smart DCA Strategy.",
            tool_trace=({"result": {"results": list(evidence)}},),
            uses_previous_response=False,
            turn_contract={"coach_evidence_plan": {"topics": variant_plan.topics}},
        ), previous_response=None, locale="nl")
        variant_answer = _minimal_read_answer(message=variant, prepared=variant_prepared)
        assert variant_answer.status == "completed"
        assert "Long term DCA BTC" in variant_answer.text
        assert "Nieuwere Smart DCA" not in variant_answer.text
    unrelated_status = {"scope": "read_bot_status", "status": "completed", "data": {
        "bot_id": 57, "operational_status": "active", "read_at": "2026-11-25T19:00:00+00:00",
    }}
    assert "Long term DCA BTC" in render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=(*evidence, unrelated_status),
        question=other_wording,
    )
    prepared = SimpleNamespace(response=SimpleNamespace(
        text="De bot is gekoppeld aan Fantasie Plan en Fantasie Strategy.",
        tool_trace=({"result": {"results": list(evidence)}},),
        uses_previous_response=False,
        turn_contract={"coach_evidence_plan": {"topics": plan.topics}},
    ), previous_response=None, locale="nl")
    verified = _minimal_read_answer(message=other_wording, prepared=prepared)
    assert verified.status == "completed"
    assert "Long term DCA BTC" in verified.text
    assert "Fantasie Plan" not in verified.text
    portfolio_only = SimpleNamespace(response=SimpleNamespace(
        text="De bot gebruikt Nieuwere Smart DCA.",
        tool_trace=({"result": {"results": [evidence[2]]}},),
        uses_previous_response=False,
        turn_contract={"coach_evidence_plan": {"topics": plan.topics}},
    ), previous_response=None, locale="nl")
    assert "Long term DCA BTC" in _minimal_read_answer(
        message=other_wording, prepared=portfolio_only,
    ).text
    inactive = (evidence[0], evidence[1], {**evidence[2], "data": {
        "bots": [{**evidence[2]["data"]["bots"][0], "is_active": False}],
    }})
    assert render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=inactive, question=question,
    ) is None
    pair_question = (
        "Welke setup en strategie zijn aan mijn BTC Paper-bot voor BTC/USDT gekoppeld? "
        "Lees alleen."
    )
    assert render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=evidence, question=pair_question,
    ) is None
    wrong_pair = (evidence[0], evidence[1], {**evidence[2], "data": {
        "bots": [{**evidence[2]["data"]["bots"][0], "pair": "BTC/EUR"}],
    }})
    assert render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=wrong_pair, question=pair_question,
    ) is None
    pair_prepared = SimpleNamespace(response=SimpleNamespace(
        text="De bot hoort bij BTC EUR DCA.",
        tool_trace=({"result": {"results": list(wrong_pair)}},),
        uses_previous_response=False,
        turn_contract={"coach_evidence_plan": {"topics": plan.topics}},
    ), previous_response=None, locale="nl")
    assert _minimal_read_answer(message=pair_question, prepared=pair_prepared).status == "unavailable"
    ambiguous = (evidence[0], evidence[1], {**evidence[2], "data": {
        "bots": [*evidence[2]["data"]["bots"], {
            "bot_id": 57, "name": "Andere BTC-bot", "symbol": "BTC", "is_live": False,
            "is_active": True,
            "setup_id": 20, "setup_name": "Nieuwere Smart DCA",
            "strategy_id": 30, "strategy_name": "Nieuwere Smart DCA Strategy",
        }],
    }})
    assert render_coach_source_fallback(
        asset="BTC", topics=plan.topics, evidence=ambiguous, question=question,
    ) is None


def test_coach_coverage_rejects_omitted_sources_and_answer_parts():
    plan = coach_evidence_plan(
        "Waarom blokkeerde mijn AAPL-bot bij mijn score en rapport? Wat doe ik nu?",
        named_asset_count=1, read_only=True,
    )
    assert plan is not None
    contract = {"coach_evidence_plan": {
        "topics": plan.topics, "read_tools": plan.read_tools,
        "decision_required": plan.decision_required,
        "next_step_required": plan.next_step_required,
    }, "attempted_scopes": []}
    assert turn_contract_gap(contract, "De score past niet; wacht.") == "coach_sources_not_checked"
    contract["attempted_scopes"] = list(plan.read_tools)
    assert turn_contract_gap(contract, "De score past niet; wacht.") == "coach_topic_missing:bot"
    assert turn_contract_gap(contract, "De setupscore past niet en de bot wacht. "
                             "Het rapport is ouder.") == "coach_bot_decision_missing"
    assert turn_contract_gap(contract, "De setupscore past niet. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder.") == "coach_next_step_missing"
    assert turn_contract_gap(contract, "De setupscore past niet. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder. "
                             "Wacht tot de opening en controleer opnieuw.") is None
    contract["coach_evidence_plan"]["benchmark_score"] = 52.7
    assert turn_contract_gap(contract, "De setupscore past niet. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder. "
                             "Wacht tot de opening en controleer opnieuw.") == "coach_verified_score_missing"
    assert turn_contract_gap(contract, "De setupscore is 52,7. De botbeslissing heeft "
                             "als reden een gesloten beurs. Het rapport is ouder. "
                             "Wacht tot de opening en controleer opnieuw.") is None


def test_coach_source_recovery_separates_quote_bot_report_and_missing_score():
    evidence = (
        {"scope": "read_active_setup", "status": "completed", "data": {
            "symbol": "AAPL", "name": "AAPL plan", "min_benchmark_score": 61, "max_benchmark_score": 75}},
        {"scope": "read_asset_scores", "status": "unavailable", "reason": "source_unavailable"},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                                      "decision_at": "2026-11-19T20:30:00+00:00",
                                      "safety_reason": "Reguliere sessie gesloten; actuele koers ontbreekt"}]}},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "symbol": "AAPL", "generated_at": "2026-11-19T19:08:00+00:00"}},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "price": 349.34, "quote_currency": "USD",
            "source_observed_at": "2026-11-19T20:29:00+00:00"}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 10005.45}, "read_at": "2026-11-19T21:00:00+00:00"}},
    )
    answer = render_coach_source_fallback(
        asset="AAPL", topics=("setup", "score", "bot", "report", "quote", "portfolio"),
        evidence=evidence, user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    for fragment in ("61–75", "geen verifieerbare actuele score", "21:30:00 CET",
                     "Reguliere sessie gesloten", "20:08:00 CET", "349,34 USD",
                     "21:29:00 CET", "10005,45"):
        assert fragment in answer


def test_repeated_source_reads_do_not_make_one_bot_and_portfolio_ambiguous():
    decision = {"scope": "read_review_history", "status": "completed", "data": {
        "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
            "decision_at": "2026-11-20T17:45:31+00:00",
            "safety_reason": "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark."}]}}
    portfolio = {"scope": "read_portfolio", "status": "completed", "data": {
        "bots": [{"symbol": "AAPL", "name": "AAPL Paper", "is_live": False,
                  "paper_cash_eur": 405.48}],
        "read_at": "2026-11-20T17:50:00+00:00"}}
    evidence = (decision, portfolio, decision, portfolio)
    assert coach_source_coverage_gap(
        asset="AAPL", topics=("bot", "portfolio"), evidence=evidence,
        answer="De bot deed geen koopvoorstel.",
    ) == "saved_bot_reason_missing"
    answer = render_coach_source_fallback(
        asset="AAPL", topics=("bot", "portfolio"), evidence=evidence,
    )
    assert answer is not None
    assert "Opgeslagen setupvoorwaarden passen niet" in answer
    assert "€405,48" in answer
    assert "geen eenduidig opgeslagen besluit" not in answer
    assert "benchmark.." not in answer


def test_coach_answer_recovery_preserves_exact_bot_reason_and_bot_cash():
    evidence = (
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                "decision_at": "2026-11-20T17:45:00+00:00",
                "safety_reason": "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark."}]}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 10005.45},
            "bots": [{"name": "AAPL Paper", "symbol": "AAPL", "is_live": False,
                      "paper_cash_eur": 405.48}],
            "read_at": "2026-11-20T17:50:00+00:00"}},
    )
    topics = ("bot", "portfolio")
    assert coach_source_coverage_gap(
        asset="AAPL", topics=topics, evidence=evidence,
        answer="De bot deed geen koopvoorstel; de kas kon ik niet lezen.",
    ) == "saved_bot_reason_missing"
    answer = render_coach_source_fallback(asset="AAPL", topics=topics, evidence=evidence)
    assert answer is not None
    assert "Opgeslagen setupvoorwaarden passen niet" in answer
    assert "AAPL Paper botkas (Paper): €405,48" in answer
    assert "Paper-portefeuille: kas €10005,45" in answer
    assert coach_source_coverage_gap(
        asset="AAPL", topics=topics, evidence=evidence, answer=answer,
    ) is None


def test_filtered_bot_cash_is_never_labelled_account_total():
    evidence = ({"scope": "read_portfolio", "status": "completed", "asset": "BTC",
                 "data": {"global": {"cash_balance": 9599.97},
                          "bots": [{"name": "BTC Paper", "symbol": "BTC",
                                    "is_live": False, "paper_cash_eur": 9599.97}]}},)
    answer = render_coach_source_fallback(
        asset="BTC", topics=("portfolio",), evidence=evidence,
    )
    assert "BTC Paper botkas (Paper): €9599,97" in answer
    assert "Paper-portefeuille: kas" not in answer


def test_coach_recovery_includes_requested_position_and_rounds_money():
    evidence = ({"scope": "read_portfolio", "status": "completed", "data": {
        "global": {"cash_balance": 10005.449999999999},
        "bots": [{"name": "AAPL Paper", "symbol": "AAPL", "is_live": False,
                  "paper_cash_eur": 405.48, "position_qty": 0}],
        "read_at": "2026-11-20T19:00:00+00:00",
    }},)
    assert coach_source_coverage_gap(
        asset="AAPL", topics=("portfolio",), evidence=evidence,
        question="Wat is mijn Paper-bottegoed en positie?",
        answer="De AAPL-botkas is €405,48.",
    ) == "paper_bot_position_missing"
    assert coach_source_coverage_gap(
        asset="AAPL", topics=("portfolio",), evidence=evidence,
        question="Wat is mijn Paper-bottegoed en positie?",
        answer="De kas is €10005,449999999999 en de positie is 0 AAPL.",
    ) == "money_precision_invalid"
    answer = render_coach_source_fallback(
        asset="AAPL", topics=("portfolio",), evidence=evidence,
    )
    assert "€10005,45" in answer
    assert "0 AAPL open" in answer
    assert "10005,449999" not in answer
    assert coach_source_coverage_gap(
        asset="AAPL", topics=("portfolio",), evidence=evidence,
        question="Wat is mijn Paper-bottegoed en positie?", answer=answer,
    ) is None


def test_coach_recovery_names_unverified_position_without_paper_cash():
    evidence = ({"scope": "read_review_history", "status": "completed", "data": {
        "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                                  "decision_at": "2026-11-20T19:00:00+00:00"}],
    }}, {"scope": "read_portfolio", "status": "completed", "data": {
        "global": {"cash_balance": None}, "bots": [],
    }})
    answer = render_coach_source_fallback(
        asset="AAPL", topics=("bot", "portfolio"), evidence=evidence,
    )
    assert "Paper-positie: geen verifieerbare hoeveelheid" in answer


def test_paper_hold_recovery_separates_budget_invested_cash_status_and_source_times():
    question = ("Beoordeel het laatste Paper-Holdbesluit van mijn bestaande Strategie long term dca btc Bot "
                "voor BTC. Lees de actuele botstatus en exacte blokkadereden opnieuw. Scheid de ingestelde "
                "botbudgetlimiet, werkelijk belegd, botkas en totale Paper-kas, en noem de bronmomenten. "
                "Geef één concrete veilige vervolgstap. Lees alleen; wijzig geen strategie, bot of order.")
    evidence = (
        {"scope": "read_bot_status", "status": "completed", "asset": "BTC", "data": {
            "bot_id": 56, "operational_status": "active", "read_at": "2026-11-24T19:09:30+00:00"}},
        {"scope": "read_review_history", "status": "completed", "asset": "BTC", "data": {
            "latest_bot_decisions": [{"bot_id": 56, "symbol": "BTC", "action": "hold",
                "decision_at": "2026-11-24T19:03:29+00:00",
                "safety_reason": "Bevestig eerst de valuta van de opgeslagen koersniveaus in de strategie."}]}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 10000}, "read_at": "2026-11-24T19:09:28+00:00",
            "bots": [{"bot_id": 56, "name": "Strategie long term dca btc Bot", "symbol": "BTC",
                      "is_live": False, "budget_total_eur": 1000, "invested_eur": 0,
                      "paper_cash_eur": 10000, "position_qty": 0}]}}
    )
    topics = ("bot", "portfolio")
    incomplete = "De botbeslissing is hold. De botkas en totale Paper-kas zijn €10000,00."
    assert coach_source_coverage_gap(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        answer=incomplete, user_time_zone="Europe/Amsterdam",
    ) is not None
    answer = render_coach_source_fallback(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    for fragment in ("botbudgetlimiet: €1000,00", "werkelijk belegd (Paper): €0,00",
                     "botkas (Paper): €10000,00", "Paper-portefeuille: kas €10000,00",
                     "Botstatus: active, uitgelezen op 2026-11-24 20:09:30 CET",
                     "hold op 2026-11-24 20:03:29 CET", "valuta van de instap-"):
        assert fragment in answer
    assert coach_source_coverage_gap(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        answer=answer, user_time_zone="Europe/Amsterdam",
    ) is None
    assert "2026-11-24 20:09:28 CET" in answer
    assert "1000,00; dit is geen extra kas" in answer
    tampered = ("Botstatus: active, uitgelezen op 2026-11-24 20:09:30 CET. "
                "Botbeslissing hold: Bevestig eerst de valuta van de opgeslagen koersniveaus in de strategie. "
                "Botbudgetlimiet €9999,00; werkelijk belegd €123,00; botkas €10000,00. "
                "Veilige vervolgstap: controleer een verse score.")
    assert coach_source_coverage_gap(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        answer=tampered, user_time_zone="Europe/Amsterdam",
    ) == "bot_budget_mismatch"
    other_zone = render_coach_source_fallback(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        user_time_zone="America/New_York",
    )
    assert "2026-11-24 14:09:30 EST" in other_zone
    assert "20:09:30 CET" not in other_zone


def test_why_no_order_coach_uses_decision_reason_and_cash_evidence_together():
    question = (
        "Waarom heeft mijn BTC Paper-bot geen order geplaatst? Leg ook uit hoeveel "
        "van de budgetlimiet echt belegd is en hoeveel Paper-kas er is. "
        "Wat is één veilige volgende stap? Lees alleen."
    )
    evidence = (
        {"scope": "read_review_history", "status": "completed", "asset": "BTC",
         "data": {"latest_bot_decisions": [{"bot_id": 56, "symbol": "BTC",
             "action": "hold", "decision_at": "2026-11-25T14:18:42+00:00",
             "safety_reason": "Bevestig eerst de valuta van de opgeslagen koersniveaus in de strategie."}]}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 10000}, "read_at": "2026-11-25T14:31:29+00:00",
            "bots": [{"bot_id": 56, "name": "BTC Paper-bot", "symbol": "BTC",
                      "is_live": False, "budget_total_eur": 1000,
                      "invested_eur": 0, "paper_cash_eur": 10000,
                      "position_qty": 0}]}}
    )
    answer = render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=evidence,
        question=question, user_time_zone="Europe/Amsterdam",
    )
    assert answer is not None
    for fragment in ("hold op 2026-11-25 15:18:42 CET",
                     "Bevestig eerst de valuta van de opgeslagen koersniveaus",
                     "botbudgetlimiet: €1000,00", "werkelijk belegd (Paper): €0,00",
                     "botkas (Paper): €10000,00", "Paper-portefeuille: kas €10000,00"):
        assert fragment in answer
    assert coach_source_coverage_gap(
        asset="BTC", topics=("bot", "portfolio"), evidence=evidence,
        question=question, answer=answer, user_time_zone="Europe/Amsterdam",
    ) is None
    extra_bot = {"bot_id": 57, "name": "Andere BTC Paper-bot", "symbol": "BTC",
                 "is_live": False, "budget_total_eur": 500, "invested_eur": 0,
                 "paper_cash_eur": 500, "position_qty": 0}
    ambiguous = (evidence[0], {**evidence[1], "data": {
        **evidence[1]["data"], "bots": [*evidence[1]["data"]["bots"], extra_bot],
    }})
    assert render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=ambiguous,
        question=question, user_time_zone="Europe/Amsterdam",
    ) is None
    punctuation_variant = (
        "Waarom heeft mijn BTC Paper-bot, volgens mijn laatste botbeslissing, "
        "geen order geplaatst? Hoeveel van de budgetlimiet is belegd en "
        "hoeveel Paper-kas is er? Lees alleen."
    )
    assert render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=ambiguous,
        question=punctuation_variant, user_time_zone="Europe/Amsterdam",
    ) is None
    cash_only_variant = (
        "Waarom heeft mijn BTC Paper-bot geen order geplaatst? "
        "Hoeveel Paper-kas is er? Lees alleen."
    )
    assert render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=ambiguous,
        question=cash_only_variant, user_time_zone="Europe/Amsterdam",
    ) is None
    assert coach_source_coverage_gap(
        asset="BTC", topics=("bot", "portfolio"), evidence=ambiguous,
        question=cash_only_variant,
        answer="Bot 56 hield aan en botkas van beide bots is €10500.",
        user_time_zone="Europe/Amsterdam",
    ) == "bot_evidence_ambiguous"
    compound_variant = "Waarom staat mijn BTC-botbeslissing op Hold? Hoeveel Paper-kas is er? Lees alleen."
    assert render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=ambiguous,
        question=compound_variant, user_time_zone="Europe/Amsterdam",
    ) is None
    assert coach_source_coverage_gap(
        asset="BTC", topics=("bot", "portfolio"), evidence=ambiguous,
        question=compound_variant, answer="De BTC-botbeslissing was Hold; de kas is €10500,00.",
        user_time_zone="Europe/Amsterdam",
    ) == "bot_evidence_ambiguous"
    named_compound = "Waarom is de BTC-botbeslissing van Alpha een Hold? Hoeveel Paper-kas is er?"
    beta_only = (evidence[0], {**evidence[1], "data": {
        **evidence[1]["data"], "bots": [extra_bot],
    }})
    assert render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=beta_only,
        question=named_compound, user_time_zone="Europe/Amsterdam",
    ) is None
    named_bot = {**evidence[1]["data"]["bots"][0], "name": "BTC Paper-bot Alpha"}
    explicit = (evidence[0], {**evidence[1], "data": {
        **evidence[1]["data"], "bots": [named_bot, extra_bot],
    }})
    explicit_question = (
        "Waarom heeft mijn BTC Paper-bot Alpha geen order geplaatst? "
        "Hoeveel van de budgetlimiet is belegd en hoeveel Paper-kas is er? "
        "Wat is één veilige vervolgstap? Lees alleen."
    )
    explicit_answer = render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=explicit,
        question=explicit_question, user_time_zone="Europe/Amsterdam",
    )
    assert explicit_answer is not None
    assert "BTC Paper-bot Alpha botkas (Paper): €10000,00" in explicit_answer
    assert "Andere BTC Paper-bot" not in explicit_answer
    no_decision = ({**evidence[0], "data": {"latest_bot_decisions": []}}, evidence[1])
    assert render_coach_source_fallback(
        asset="BTC", topics=("bot", "portfolio"), evidence=no_decision,
        question=question, user_time_zone="Europe/Amsterdam",
    ) is None


def test_paper_hold_fallback_rejects_two_bots_with_conflicting_source_ids():
    question = ("Beoordeel het laatste Paper-Holdbesluit van mijn BTC Bot Alpha voor BTC/USDT. "
                "Lees de botstatus, budgetlimiet en Paper-kas. Lees alleen.")
    evidence = (
        {"scope": "read_review_history", "status": "completed", "asset": "BTC", "data": {
            "latest_bot_decisions": [{"symbol": "BTC", "bot_id": 1, "pair": "BTC/USDT", "action": "hold",
                "safety_reason": "Koersniveauvaluta onbevestigd"}]}},
        {"scope": "read_bot_status", "status": "completed", "asset": "BTC", "data": {
            "bot_id": 2, "operational_status": "active", "read_at": "2026-11-24T19:09:30+00:00"}},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "global": {"cash_balance": 12000}, "read_at": "2026-11-24T19:09:28+00:00",
            "bots": [
                {"bot_id": 1, "name": "BTC Bot Alpha", "symbol": "BTC", "quote_currency": "USDT",
                 "is_live": False, "budget_total_eur": 1000, "paper_cash_eur": 10000},
                {"bot_id": 2, "name": "BTC Bot Beta", "symbol": "BTC", "quote_currency": "EUR",
                 "is_live": False, "budget_total_eur": 2000, "paper_cash_eur": 2000},
            ]}},
    )
    topics = ("bot", "portfolio")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        user_time_zone="Europe/Amsterdam",
    ) is None
    assert coach_source_coverage_gap(
        asset="BTC", topics=topics, evidence=evidence, question=question,
        answer="BTC Bot Alpha wacht; budgetlimiet €1000,00 en kas €10000,00.",
        user_time_zone="Europe/Amsterdam",
    ) == "bot_evidence_ambiguous"
    correct_status = {**evidence[1], "data": {**evidence[1]["data"], "bot_id": 1}}
    other_decision = {"symbol": "BTC", "bot_id": 2, "pair": "BTC/EUR", "action": "hold",
                      "safety_reason": "Andere botreden"}
    mixed_history = {**evidence[0], "data": {
        "latest_bot_decisions": [*evidence[0]["data"]["latest_bot_decisions"], other_decision]}}
    selected = render_coach_source_fallback(
        asset="BTC", topics=topics, evidence=(mixed_history, correct_status, evidence[2]),
        question=question, user_time_zone="Europe/Amsterdam",
    )
    assert selected is not None
    assert "BTC Bot Alpha" in selected
    assert "BTC Bot Beta" not in selected
    assert "Andere botreden" not in selected
    wrong_named_question = question.replace("BTC Bot Alpha", "BTC Bot Gamma")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][0]]}}),
        question=wrong_named_question, user_time_zone="Europe/Amsterdam",
    ) is None
    longer_wrong_name = question.replace("BTC Bot Alpha", "BTC Bot Alpha Longterm")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][1]]}}),
        question=longer_wrong_name, user_time_zone="Europe/Amsterdam",
    ) is None
    dotted_wrong_name = question.replace("BTC Bot Alpha", "DCA 2.0 Bot Alpha")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][1]]}}),
        question=dotted_wrong_name, user_time_zone="Europe/Amsterdam",
    ) is None
    no_pronoun_name = ("Beoordeel DCA 2.0 Bot Alpha voor BTC in mijn account. "
                       "Lees de botstatus, budgetlimiet, botkas en totale Paper-kas.")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][1]]}}),
        question=no_pronoun_name, user_time_zone="Europe/Amsterdam",
    ) is None
    account_phrase = ("Beoordeel DCA 2.0 Bot Alpha in mijn BTC-account. "
                      "Lees het Paper-Holdbesluit, botstatus, budgetlimiet, botkas en totale Paper-kas.")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][1]]}}),
        question=account_phrase, user_time_zone="Europe/Amsterdam",
    ) is None
    negated_bot = ("Beoordeel niet BTC Bot Beta; beoordeel DCA 2.0 Bot Alpha in mijn BTC-account. "
                   "Lees het Paper-Holdbesluit, botstatus, budgetlimiet, botkas en totale Paper-kas.")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][1]]}}),
        question=negated_bot, user_time_zone="Europe/Amsterdam",
    ) is None
    prefix_name = question.replace("BTC Bot Alpha", "BTC Bot Alpha Longterm")
    assert render_coach_source_fallback(
        asset="BTC", topics=topics,
        evidence=(evidence[0], correct_status, {**evidence[2], "data": {
            **evidence[2]["data"], "bots": [evidence[2]["data"]["bots"][0]]}}),
        question=prefix_name, user_time_zone="Europe/Amsterdam",
    ) is None


def test_paper_hold_chat_recovery_replaces_tampered_values_and_fails_closed_on_wrong_bot():
    question = ("Beoordeel het laatste Paper-Holdbesluit van mijn BTC Bot Alpha voor BTC. "
                "Lees de actuele botstatus en blokkadereden. Scheid botbudgetlimiet, werkelijk belegd, "
                "botkas en totale Paper-kas. Geef één concrete veilige vervolgstap. Lees alleen.")
    decision = {"scope": "read_review_history", "status": "completed", "asset": "BTC", "data": {
        "latest_bot_decisions": [{"bot_id": 1, "symbol": "BTC", "pair": "BTC/USDT", "action": "hold",
            "decision_at": "2026-11-24T19:03:29+00:00",
            "safety_reason": "Bevestig eerst de valuta van de opgeslagen koersniveaus in de strategie."}]}}
    status = {"scope": "read_bot_status", "status": "completed", "asset": "BTC", "data": {
        "bot_id": 1, "operational_status": "active", "read_at": "2026-11-24T19:09:30+00:00"}}
    portfolio = {"scope": "read_portfolio", "status": "completed", "data": {
        "global": {"cash_balance": 10000}, "read_at": "2026-11-24T19:09:28+00:00",
        "bots": [{"bot_id": 1, "name": "BTC Bot Alpha", "symbol": "BTC", "is_live": False,
                  "budget_total_eur": 1000, "invested_eur": 0, "paper_cash_eur": 10000,
                  "position_qty": 0}]}}
    plan = coach_evidence_plan(question, named_asset_count=1, read_only=True)
    assert plan is not None
    assert {"read_bot_status", "read_review_history", "read_portfolio"} <= set(plan.read_tools)
    def prepared(status_read):
        return SimpleNamespace(response=SimpleNamespace(
            text=("Botstatus active, uitgelezen op 2026-11-24 20:09:30 CET. "
                  "Holdreden: Bevestig eerst de valuta van de opgeslagen koersniveaus in de strategie. "
                  "Botbudgetlimiet €9999,00; werkelijk belegd €123,00; botkas €10000,00; "
                  "totale Paper-kas €10000,00. Veilige vervolgstap: controleer een verse score."),
            tool_trace=({"result": {"results": [decision, status_read, portfolio]}},),
            uses_previous_response=False,
            turn_contract={"coach_evidence_plan": {"topics": plan.topics}},
        ), previous_response=None, locale="nl")
    repaired = _minimal_read_answer(
        message=question, prepared=prepared(status), user_time_zone="Europe/Amsterdam",
    )
    assert repaired.status == "completed"
    assert "botbudgetlimiet: €1000,00" in repaired.text
    assert "werkelijk belegd (Paper): €0,00" in repaired.text
    assert "valuta van de instap-" in repaired.text
    assert "€9999,00" not in repaired.text
    wrong_status = {**status, "data": {**status["data"], "bot_id": 2}}
    blocked = _minimal_read_answer(
        message=question, prepared=prepared(wrong_status), user_time_zone="Europe/Amsterdam",
    )
    assert blocked.status == "unavailable"
    assert blocked.reason == "coach_source_incomplete"
    missing_status = _minimal_read_answer(
        message=question, prepared=prepared({"scope": "read_bot_status", "status": "unavailable", "asset": "BTC"}),
        user_time_zone="Europe/Amsterdam",
    )
    assert missing_status.status == "unavailable"
    assert missing_status.reason == "coach_source_incomplete"
    filtered_portfolio = {**portfolio, "asset": "BTC"}
    filtered = SimpleNamespace(response=SimpleNamespace(
        text=prepared(status).response.text,
        tool_trace=({"result": {"results": [decision, status, filtered_portfolio]}},),
        uses_previous_response=False,
        turn_contract={"coach_evidence_plan": {"topics": plan.topics}},
    ), previous_response=None, locale="nl")
    no_total = _minimal_read_answer(
        message=question, prepared=filtered, user_time_zone="Europe/Amsterdam",
    )
    assert no_total.status == "unavailable"
    assert no_total.reason == "coach_source_incomplete"
