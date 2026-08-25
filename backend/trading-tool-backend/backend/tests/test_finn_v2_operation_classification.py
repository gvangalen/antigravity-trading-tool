import pytest

from backend.services.finn_v2_operation_classification_service import (
    FinnV2OperationClassificationService,
)


CLASSIFIER = FinnV2OperationClassificationService()


@pytest.mark.parametrize(
    ("operation_id", "messages"),
    [
        ("capability", (
            "Wat kan FINN doen?", "Waarmee kan FINN helpen?", "Hoe helpt FINN mij?",
            "Welke mogelijkheden heeft FINN?", "What can FINN do?", "Help me begrijpen wat FINN kan.",
        )),
        ("read_active_asset", (
            "Welke asset staat actief?", "Welk instrument is geselecteerd?", "Welke coin volg ik?",
            "Welk aandeel bekijk ik?", "Waar staat mijn workspace op?", "Welke markt is actief?",
        )),
        ("read_indicator_configuration", (
            "Welke indicatoren zijn ingesteld?", "Toon mijn indicatorconfiguratie.", "Welke signalen gebruik ik?",
            "Hoe zijn mijn indicatoren geconfigureerd?", "Welke volume-indicator volg ik?", "Welke trendindicatoren gebruik ik?",
        )),
        ("read_active_setup", (
            "Welke setup gebruik ik?", "Toon mijn actieve setup.", "Welke setup staat voor BTC actief?",
            "Laat de huidige setup zien.", "Wat is mijn setup?", "Welke set-up heb ik?",
        )),
        ("evaluate_plan", (
            "Beoordeel mijn volledige plan.", "Waar zit het zwakke punt in mijn plan?", "Past mijn plan bij mijn profiel?",
            "Welke voorwaarde ontbreekt in mijn plan?", "Hoe betrouwbaar is mijn plan?", "Bekijk mijn BTC-plan en noem het risico.",
        )),
        ("create_setup", (
            "Maak een setup voor BTC.", "Ontwerp een nieuwe BTC-setup.", "Stel een setup voor BTC voor.",
            "Bereid een setup voor BTC voor.", "Create a BTC setup.", "Maak een setupconcept voor BTC.",
        )),
        ("watchlist_add", (
            "Voeg ADA toe aan mijn watchlist.", "Add ADA to my watchlist.", "Zet ADA op mijn volglijst.",
            "Voeg ADA toe aan de watchlist.", "Ik wil ADA aan mijn watchlist toevoegen.", "Volg ADA in mijn watchlist.",
        )),
        ("watchlist_remove", (
            "Verwijder ADA uit mijn watchlist.", "Remove ADA from my watchlist.", "Haal ADA van mijn volglijst.",
            "Verwijder ADA van de watchlist.", "Ik wil ADA uit mijn watchlist halen.", "Stop met ADA volgen in mijn watchlist.",
        )),
        ("activate_bot", (
            "Activeer mijn bot live.", "Schakel mijn bot live.", "Start mijn bot live.",
            "Zet mijn bot live.", "Activate my bot live.", "Maak deze bot live.",
        )),
    ],
)
def test_semantic_operation_paraphrases_select_one_contract(operation_id, messages):
    assert {CLASSIFIER.classify(message=message).operation_id for message in messages} == {operation_id}


@pytest.mark.parametrize(
    ("operation_id", "messages"),
    [
        ("explain_previous_evidence", (
            "Onderbouw die conclusie.", "Waar baseer je dat op?", "Welk bewijs ondersteunt dit?",
            "Waarom concludeerde je dat?", "Leg de eerdere conclusie uit.", "Toon de evidence achter dat antwoord.",
        )),
        ("reformulate_previous_response", (
            "Formuleer dat korter.", "Zeg die conclusie anders.", "Herformuleer het vorige antwoord.",
            "Kun je dit compacter maken?", "Vertel dat in andere woorden.", "Maak de eerdere conclusie korter.",
        )),
    ],
)
def test_follow_up_paraphrases_keep_the_verified_conversation_lineage(operation_id, messages):
    context = {
        "last_verified_context": {
            "verified_response_id": "verified-btc-1",
            "operation_id": "evaluate_plan",
            "mode": "EVALUATE",
            "conclusion": "A grounded conclusion.",
            "evidence_refs": ["artifact-1"],
        },
    }

    assert {
        CLASSIFIER.classify(message=message, conversation_context=context).operation_id
        for message in messages
    } == {operation_id}


def test_target_polarity_is_not_reversed_by_workspace_context():
    add = CLASSIFIER.classify(message="Voeg ADA toe aan mijn watchlist.")
    remove = CLASSIFIER.classify(message="Verwijder ADA uit mijn watchlist.")

    assert add.action == "add"
    assert add.operation_id == "watchlist_add"
    assert remove.action == "remove"
    assert remove.operation_id == "watchlist_remove"


@pytest.mark.parametrize("message", ("Maak iets nieuws.", "Wijzig mijn instellingen.", "Voeg iets toe."))
def test_ambiguous_action_without_a_domain_remains_a_clarification(message):
    assert CLASSIFIER.classify(message=message).operation_id == "clarify_request"


def test_complete_graph_request_uses_the_plan_contract():
    result = CLASSIFIER.classify(message="Welke setup, strategie en bot heb ik voor mijn actieve asset?")

    assert result.operation_id == "read_active_plan"
