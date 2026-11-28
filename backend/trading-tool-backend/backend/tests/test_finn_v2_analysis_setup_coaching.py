from backend.services.finn_v2_analysis_setup_coaching import render_analysis_setup_coaching


def render(score, setups, language="nl"):
    return render_analysis_setup_coaching(
        subject="MSTR", matching=setups,
        scored={"source_status": "available", "benchmark_score": score},
        language=language,
    )


def test_saved_score_zone_gives_distance_and_next_step():
    setup = [{"min_benchmark_score": 50, "max_benchmark_score": 70}]
    below = render(42.7, setup)
    assert "7,3 punten onder de ondergrens van 50" in below
    assert "instapvoorwaarde, risicogrens en exit" in below
    assert "geen koopsein" not in below
    assert "binnen de opgeslagen scorezone" in render(61, setup)
    assert "5 punten boven de bovengrens van 70" in render(75, setup)


def test_missing_or_ambiguous_threshold_does_not_invent_distance():
    assert "scorezone" in render(42.7, [{"min_benchmark_score": None}])
    assert "afstand tot een scoregrens nu niet berekenen" in render(
        42.7, [{"min_benchmark_score": 75, "max_benchmark_score": 50}],
    )
    assert "2 opgeslagen setups" in render(42.7, [{}, {}])
    assert "7,3" not in render(42.7, [{}, {}])


def test_no_saved_setup_proposes_choices_without_signal_boilerplate():
    for language in ("nl", "en", "de"):
        answer = render(42.7, [], language)
        assert "DCA" in answer
        expected_score = "42.7/100" if language == "en" else "42,7/100"
        assert expected_score in answer
        assert "geen koopsein" not in answer
        assert "not a buy signal" not in answer
        assert "kein Kaufsignal" not in answer
