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


def test_minimal_live_read_completes_repeated_owner_history_reads():
    prepared = _prepared(text=(
        "Exitreden: eerste koersdoel. De opgeslagen weekreflectie over 9–15 "
        "november 2026 registreert één trade. Weekreflectie gegenereerd: "
        "16 november 2026, 05:15 UTC (06:15 CET, Amsterdamse tijd)."
    ))
    prepared.response.tool_trace += prepared.response.tool_trace
    answer = _minimal_read_answer(
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
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
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
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
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
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
    ):
        answer = _minimal_read_answer(
            message=QUESTION, prepared=_prepared(text=(
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


def test_historical_week_fx_moment_completion_is_idempotent():
    from backend.services.finn_v2_factual_source_answer import complete_historical_week_exit_moments

    prepared = _prepared(text="FX-bronmoment: 12 november 14:03 UTC.")
    evidence = tuple(prepared.response.tool_trace[0]["result"]["results"])
    first = complete_historical_week_exit_moments(
        prepared.response.text, evidence, question=QUESTION,
        user_time_zone="Europe/Amsterdam",
    )
    second = complete_historical_week_exit_moments(
        first, evidence, question=QUESTION, user_time_zone="Europe/Amsterdam",
    )
    assert second == first
    assert first.count("Geverifieerd FX-bronmoment") == 1
    assert "14:03 UTC" not in first


def test_historical_week_fx_scrub_preserves_next_labeled_source_after_comma():
    for claim, bot_moment in (
        ("FX-bronmoment: 12 november 14:02 UTC", "botbeslissing: 12 november 14:59 UTC"),
        ("Wisselkoersbron bij uitvoering: 12 november 14:03 UTC",
         "botbeslissing 12 november 14:59 UTC"),
    ):
        answer = _minimal_read_answer(
            message=QUESTION, prepared=_prepared(text=f"{claim}, {bot_moment}."),
            user_time_zone="Europe/Amsterdam",
        )
        assert answer.status == "completed", answer.reason
        assert bot_moment in answer.text
        assert answer.text.count("Geverifieerd FX-bronmoment") == 1
        if "14:03" in claim:
            assert "14:03 UTC" not in answer.text
        else:
            assert claim in answer.text


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
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "Geverifieerd FX-bronmoment" not in answer.text
    assert "14:04 UTC" not in answer.text
    assert "FX-bronmoment uit antwoordtekst niet geverifieerd" in answer.text


def test_minimal_live_read_neutralizes_fx_clock_when_source_missing():
    prepared = _prepared(text="FX-bron: 12 november 14:04 UTC.")
    prepared.response.tool_trace[0]["result"]["results"][0]["data"]["closed_trades"][0][
        "paper_exit_evidence"
    ] = None
    answer = _minimal_read_answer(
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "14:04 UTC" not in answer.text
    assert "Geverifieerd FX-bronmoment" not in answer.text


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
        message=QUESTION, prepared=prepared, user_time_zone="Europe/Amsterdam",
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
            message=QUESTION, prepared=conflicting_identity,
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
        message=QUESTION, prepared=conflicting_outside_week,
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
        message=QUESTION, prepared=separate_old_dossier,
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
        message=QUESTION, prepared=conflicting_trade,
        user_time_zone="Europe/Amsterdam",
    )
    assert answer.status == "completed", answer.reason
    assert "als gesloten geregistreerd" not in answer.text
