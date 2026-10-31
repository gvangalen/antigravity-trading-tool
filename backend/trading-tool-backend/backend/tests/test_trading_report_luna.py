from types import SimpleNamespace
from datetime import date, timedelta

import pytest

from backend.services import finn_unified_report_service as reports
from backend.utils import openai_client

TRADING_REPORT_MODEL = "gpt-6-luna"
TRADING_REPORT_REASONING_EFFORT = "none"


def _stub_report_provider(monkeypatch, output_text):
    requests = []

    class Responses:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                output_text=output_text,
                model="gpt-6-luna",
                usage=SimpleNamespace(input_tokens=21, output_tokens=13),
            )

    monkeypatch.setattr(openai_client, "client", SimpleNamespace(responses=Responses()))
    monkeypatch.setattr(openai_client, "get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(openai_client, "_rate_limit_allows_call", lambda: True)
    monkeypatch.setattr(openai_client, "_quota_breaker_active", lambda: False)
    monkeypatch.setattr(openai_client, "_log_openai_usage", lambda **kwargs: None)
    return requests


def test_report_json_uses_luna_responses_without_legacy_sampling(monkeypatch):
    requests = _stub_report_provider(monkeypatch, '{"executive_summary":"Markets are mixed."}')

    result = openai_client.ask_gpt_json(
        prompt="Write a JSON report", system_role="Report writer", max_tokens=3000,
        model_override=TRADING_REPORT_MODEL, reasoning_effort=TRADING_REPORT_REASONING_EFFORT,
    )

    assert result == {"executive_summary": "Markets are mixed."}
    assert requests == [{
        "model": "gpt-6-luna",
        "input": [
            {"role": "system", "content": "Report writer"},
            {"role": "user", "content": "Write a JSON report\n\nRETURN ONLY VALID JSON."},
        ],
        "reasoning": {"effort": "none"},
        "max_output_tokens": 3000,
        "text": {"format": {"type": "json_object"}},
    }]


def test_report_text_uses_luna_responses(monkeypatch):
    requests = _stub_report_provider(monkeypatch, "The market is mixed. ")

    result = openai_client.ask_gpt_text(
        prompt="Summarize the week", system_role="Report writer",
        model_override=TRADING_REPORT_MODEL, reasoning_effort=TRADING_REPORT_REASONING_EFFORT,
    )

    assert result == "The market is mixed."
    assert requests[0]["model"] == "gpt-6-luna"
    assert requests[0]["reasoning"] == {"effort": "none"}
    assert "text" not in requests[0]
    assert "temperature" not in requests[0]


def test_shared_client_default_uses_luna_responses(monkeypatch):
    requests = _stub_report_provider(monkeypatch, "FINN answer")

    assert openai_client.ask_gpt_text(prompt="Question", system_role="General") == "FINN answer"
    assert requests[0]["model"] == "gpt-6-luna"
    assert requests[0]["reasoning"] == {"effort": "none"}


def test_all_trading_report_generators_pin_luna(monkeypatch):
    captured = []
    shared = {"locale": "nl", "observed_at": "2026-10-07", "assets": []}

    async def load_daily(_user_id, period="daily"):
        return shared

    monkeypatch.setattr(reports, "_load_context", load_daily)
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **kwargs: captured.append(kwargs) or {})
    for generate in (
        reports.generate_unified_daily_report_sections,
        reports.generate_weekly_report_sections,
        reports.generate_monthly_report_sections,
        reports.generate_quarterly_report_sections,
    ):
        generate(7)
    assert len(captured) == 4
    assert all(call["model_override"] == "gpt-6-luna" for call in captured)
    assert all(call["reasoning_effort"] == "none" for call in captured)


@pytest.mark.parametrize("period", ["weekly", "monthly", "quarterly"])
def test_period_comparison_uses_only_dated_same_pair_scores(period):
    start = reports._period_start(period, date.today())
    before = (start - timedelta(days=1)).isoformat()
    within = start.isoformat()
    context = {"report_previous": [
        {"report_date": before, "snapshot": {"assets": [
            {"pair": "BTC/EUR", "benchmark_score": 45,
             "reported_scores": {"market_score": 40}},
            {"pair": "BTC/USDT", "benchmark_score": 90,
             "reported_scores": {"market_score": 90}},
        ]}},
        {"report_date": within, "snapshot": {"assets": [
            {"pair": "BTC/EUR", "benchmark_score": 50,
             "reported_scores": {"market_score": 45}},
        ]}},
    ]}
    facts = {"assets": [{"pair": "BTC/EUR", "display_symbol": "BTC/EUR",
                         "benchmark_score": 65,
                         "scores": {"market_score": 55}}]}

    comparison = reports._report_v2_period_comparison(context, facts, period)

    assert comparison["period"] == period
    assert comparison["period_start"] == within
    assert comparison["baseline_date"] == within
    assert comparison["observation_days"] == 1
    assert comparison["changes"] == [
        {"asset": "BTC/EUR", "fact": "benchmark_score", "before": 50, "after": 65},
        {"asset": "BTC/EUR", "fact": "market_score", "before": 45, "after": 55},
    ]
    assert all(row["asset"] == "BTC/EUR" for row in comparison["period_observations"])


@pytest.mark.parametrize("locale, availability, score", [
    ("nl", "niet beschikbaar → beschikbaar", "40/100 → 20/100"),
    ("en", "unavailable → available", "40/100 → 20/100"),
    ("de", "nicht verfügbar → verfügbar", "40/100 → 20/100"),
])
def test_period_retrospective_localizes_score_changes(locale, availability, score):
    comparison = {
        "period": "weekly", "previous_date": "2026-10-30", "previous_observations": [],
        "changes": [
            {"asset": "BTC/EUR", "fact": "benchmark_availability", "before": False, "after": True},
            {"asset": "BTC/EUR", "fact": "macro_score", "before": 40.0, "after": 20.0},
        ],
    }
    facts = {"assets": []}
    context = {"report_portfolios": {}, "report_bot_status": {"bots": []}}
    text = reports._report_v2_factual_fallbacks(context, facts, comparison, locale)["retrospective"]
    assert availability in text
    assert score in text
    assert "benchmark_availability" not in text
    assert "40.0" not in text


def test_report_analysis_repairs_market_score_benchmark_conflation():
    facts = {"assets": [{"display_symbol": "BTC/EUR", "scores": {"market_score": 40},
                          "benchmark_score": 33.3, "market_snapshot": {}, "setups": []}]}
    assert reports._report_v2_analysis_claims_contradict(
        "BTC/EUR: de marktscore (benchmark) is 33,3.", facts)
    assert not reports._report_v2_analysis_claims_contradict(
        "BTC/EUR: marktscore 40; benchmarkscore 33,3.", facts)


def test_period_retrospective_rejects_raw_internal_field_names():
    assert reports._report_v2_contradicts_facts(
        "retrospective", "BTC/EUR benchmark_availability: False → True",
        {"assets": []}, {}, {})
