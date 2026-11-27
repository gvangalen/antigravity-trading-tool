from types import SimpleNamespace

from backend.services.finn_v2_run_service import _minimal_read_answer


QUESTION = (
    "Bespreek mijn afgesloten AAPL Paper-trade van 12 november en de opgeslagen "
    "weekreflectie van 9–15 november. Welke exitreden en welk concreet aandachtspunt "
    "zijn bevestigd, en wat blijft onzeker over plantrouw? Noem de bronmomenten "
    "apart. Lees alleen; wijzig niets."
)


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
                        "exit_at": trade_date,
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
            message=QUESTION, prepared=_prepared(text=text),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        # The recorded close is distinct from the model's 14:59 UTC decision.
        assert "AAPL Paper-trade als gesloten geregistreerd: 2026-11-12 16:02:00 CET" in answer.text
        assert "Geverifieerd opslagmoment week 2026-11-09 t/m 2026-11-15: 2026-11-16 06:15:00 CET" in answer.text


def test_minimal_live_read_does_not_complete_mismatched_or_missing_sources():
    text = "De AAPL-exit en weekreflectie zijn besproken."
    for prepared in (_prepared(text=text, trade_date="2026-11-05T14:59:00+00:00"),
                     _prepared(text=text, week=False)):
        answer = _minimal_read_answer(
            message=QUESTION, prepared=prepared,
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
        message=QUESTION, prepared=_prepared(text=draft),
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
