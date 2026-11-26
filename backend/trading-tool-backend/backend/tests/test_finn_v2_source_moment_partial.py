from types import SimpleNamespace

from backend.services.finn_v2_run_service import _minimal_read_answer
from backend.services.finn_v2_source_moment_partial import render_source_moment_partial


QUESTION = (
    "Mijn BTC-bot 129 wacht wegens setupmismatch; de handmatige Paper-preview "
    "blokkeert bij 35 onder 61. Het dagrapport toont BTC/EUR 36,7 en "
    "BTC/USDT 40. Moet ik nu BTC kopen? Leg het verschil tussen rapport, "
    "paaranalyse en botplan uit, en benoem mijn open ETH-positie uit de "
    "scorevrije QA-test. Geef een veilige volgende stap."
)


def _evidence():
    return (
        {"scope": "read_bot_status", "status": "completed", "asset": "BTC", "data": {
            "bot_id": 129, "operational_status": "paused",
            "read_at": "2026-11-26T16:30:00+00:00",
        }},
        {"scope": "read_review_history", "status": "completed", "asset": "BTC", "data": {
            "latest_bot_decisions": [{
                "bot_id": 129, "symbol": "BTC", "action": "hold",
                "decision_at": "2026-11-26T16:25:00+00:00",
            }],
        }},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "generated_at": "2026-11-26T05:00:00+00:00",
        }},
        {"scope": "read_asset_scores", "status": "completed", "asset": "BTC", "data": {
            "pair": "BTC/EUR", "source_status": "available", "benchmark_score": 35.0,
        }},
        {"scope": "read_asset_scores", "status": "completed", "asset": "BTC", "data": {
            "pair": "BTC/USDT", "source_status": "unverified_scores", "benchmark_score": 40.0,
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
            turn_contract=None,
        ),
    )

    answer = _minimal_read_answer(message=QUESTION, prepared=prepared)

    assert answer.status == "completed", (answer.reason, answer.rejection_details)
    assert "10:00 CET" not in answer.text
    assert "Bot #129" in answer.text
    assert "wachten" in answer.text
    assert "dagrapport" in answer.text
    assert "BTC/EUR" in answer.text and "BTC/USDT" in answer.text
    assert "BTC/EUR heeft benchmarkscore 35/100" in answer.text
    assert "BTC/USDT heeft benchmarkscore 40/100" not in answer.text
    assert "0,00644603 ETH" in answer.text
    assert "geen nieuwe koop onderbouwen" in answer.text
    assert answer.text.endswith("Welk van de genoemde handelsparen hoort bij bot #129?")


def test_partial_answer_does_not_repeat_unread_eth_position_or_bot_status():
    evidence = (_evidence()[2],)

    answer = render_source_moment_partial(question=QUESTION, evidence=evidence)

    assert answer is not None
    assert "dagrapport" in answer
    assert "ETH" not in answer
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
