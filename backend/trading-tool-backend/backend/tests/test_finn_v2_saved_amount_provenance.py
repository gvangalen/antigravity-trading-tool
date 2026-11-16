from backend.services.finn_v2_saved_amount_provenance import append_saved_amount_provenance


def _evidence(symbol="ETH", quote="EUR"):
    return (
        {"scope": "read_active_setup", "status": "completed", "data": {
            "setup_id": 41, "symbol": symbol, "quote_currency": quote,
        }},
        {"scope": "read_linked_strategy", "status": "completed", "data": {
            "setup_id": 41, "strategy_id": 51, "base_amount": 10,
            "currency": "EUR",
        }},
    )


def test_user_stated_amount_gets_explicit_saved_source_when_read_proves_it():
    answer = "Score 35 valt buiten 61–75. Een koop van €10 is nu niet geldig."
    result = append_saved_amount_provenance(
        message="Beoordeel mijn ETH/EUR-conceptsetup: is een koop van €10 volgens mijn plan geldig?",
        answer=answer, evidence=_evidence(), mentioned_assets={"ETH"}, locale="nl",
    )
    assert result == answer + "\n\nDe gekoppelde opgeslagen strategie heeft €10 als basisbedrag."


def test_saved_amount_provenance_is_generic_for_a_stock_and_locales():
    result = append_saved_amount_provenance(
        message="Is a €10 purchase according to my AAPL setup valid?",
        answer="The score is too low for a purchase of €10.",
        evidence=_evidence("AAPL", "USD"), mentioned_assets={"AAPL"}, locale="en",
    )
    assert result.endswith("The linked saved strategy has a base amount of €10.")


def test_user_amount_is_not_treated_as_saved_without_unique_matching_read():
    message = "Is a €10 purchase according to my ETH/EUR setup valid?"
    answer = "The score is too low for €10."
    for evidence in (
        (),
        _evidence()[:1],
        _evidence() + ({"scope": "read_linked_strategy", "status": "completed", "data": {
            "setup_id": 41, "strategy_id": 52, "base_amount": 10,
        }},),
        _evidence("ETH", "USDT"),
    ):
        assert append_saved_amount_provenance(
            message=message, answer=answer, evidence=evidence,
            mentioned_assets={"ETH"}, locale="en",
        ) == answer


def test_existing_explicit_saved_amount_is_not_repeated():
    answer = "De opgeslagen strategie heeft €10 als vast basisbedrag. De score is te laag."
    assert append_saved_amount_provenance(
        message="Is €10 volgens mijn ETH/EUR-plan geldig?", answer=answer,
        evidence=_evidence(), mentioned_assets={"ETH"}, locale="nl",
    ) == answer


def test_other_saved_amount_in_answer_does_not_prove_requested_amount():
    answer = "De opgeslagen botstrategie heeft €100; een koop van €10 past niet bij de score."
    result = append_saved_amount_provenance(
        message="Is €10 volgens mijn ETH/EUR-conceptsetup geldig?", answer=answer,
        evidence=_evidence(), mentioned_assets={"ETH"}, locale="nl",
    )
    assert result.endswith("De gekoppelde opgeslagen strategie heeft €10 als basisbedrag.")
