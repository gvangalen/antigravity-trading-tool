from backend.services.finn_v2_bot_subject_claims import bot_subject_supported, focused_bot_id


def _evidence():
    return ({"scope": "read_review_history", "status": "completed", "data": {
        "latest_bot_decisions": [
            {"bot_id": 129, "symbol": "BTC", "bot_name": "BTC Paper"},
            {"bot_id": 130, "symbol": "AAPL", "bot_name": "AAPL Paper"},
        ],
    }},)


def test_correction_keeps_single_explicit_prior_bot_id():
    previous = {"terminal_status": "completed", "user_message":
                "Controleer BTC-bot129 om 09:45 CET en de planscore."}
    assert focused_bot_id("Corrigeer die foutieve tijd", previous) == 129
    assert focused_bot_id("Bespreek bot 130", previous) == 130
    assert focused_bot_id("Hoe gaat het?", previous) is None
    assert focused_bot_id(
        "Ik bedoel specifiek BTC Paper-bot 129 en zijn beoordeling van 16 november "
        "om 04:15 UTC (= 05:15 CET), niet zijn nieuwste beoordeling van 15:30 CET. "
        "Laat AAPL-bot 130 buiten beschouwing."
    ) == 129
    assert focused_bot_id("Bespreek bot 129 en bot 130.") is None


def test_bot_subject_rejects_switch_to_other_saved_bot():
    assert bot_subject_supported("BTC-bot 129 gaf geen order.", _evidence(), bot_id=129)
    assert not bot_subject_supported("AAPL-bot 130 bleef wachten.", _evidence(), bot_id=129)
    assert not bot_subject_supported("De AAPL-bot bleef wachten.", _evidence(), bot_id=129)
    assert not bot_subject_supported("De bot bleef wachten.", _evidence(), bot_id=129)
    assert bot_subject_supported("BTC-bot 129 wachtte; de AAPL-bot heeft een eigen besluit.",
                                 _evidence(), bot_id=129)
    assert bot_subject_supported("BTC-bot 129 wachtte. Laat AAPL-bot 130 buiten beschouwing.",
                                 _evidence(), bot_id=129)
    assert not bot_subject_supported("BTC-bot 129 gaf geen order.", _evidence(), bot_id=999)
