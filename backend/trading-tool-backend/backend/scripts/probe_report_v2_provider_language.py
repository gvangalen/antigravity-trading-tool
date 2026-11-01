"""Synthetic, non-user Report 2.0 language probe against the real provider.

Run only in the manually dispatched CI job with its protected OpenAI secret.
No model output or credentials are printed.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date, timedelta

from backend.services import finn_unified_report_service as reports


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY unavailable for provider gate")

    context = {
        "locale": "nl",
        "observed_at": "2026-10-31T09:00:00+00:00",
        "report_portfolios": {
            "paper": {"global": {"total_equity": 300, "cash_balance": 300,
                                 "position_value": 0, "total_budget_limit": 1000}, "bots": []},
            "live": {"global": {"total_equity": None, "cash_balance": None}, "bots": []},
        },
        "report_bot_status": {"observed_at": "2026-10-31T09:00:00+00:00", "bots": []},
        "report_previous": [{
            "report_date": (date.today() - timedelta(days=offset)).isoformat(),
            "snapshot": {"assets": [{
                "pair": "BTC/EUR", "benchmark_score": 35 + offset,
                "reported_scores": {"market_score": 30 + offset,
                                    "macro_score": 20, "technical_score": 50},
            }]},
        } for offset in (2, 1)],
        "assets": [{
            "symbol": "BTC", "pair": "BTC/EUR",
            "setups": [{"id": 1, "name": "EUR Cash Builder", "setup_type": "dca",
                        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": 5}],
            "strategies": [{"id": 2, "name": "BTC DCA", "setup_id": 1,
                            "execution_mode": "fixed", "base_amount": 100}],
            "bots": [],
            "benchmark": {"source_status": "missing", "reported_scores": {},
                          "component_source_status": {}},
            "market_snapshot": {"source_status": "fresh", "change_24h": -0.295},
        }, {
            "symbol": "BTC", "pair": "BTC/USDT",
            "setups": [{"id": 3, "name": "USDT Cash Builder", "setup_type": "dca",
                        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": 1}],
            "strategies": [], "bots": [],
            "benchmark": {"source_status": "missing", "reported_scores": {},
                          "component_source_status": {}},
            "market_snapshot": {"source_status": "fresh", "change_24h": 0.354},
        }],
    }
    reports._load_context = lambda _user_id, _period="daily": asyncio.sleep(0, result=context)
    provider_result = []
    real_ask = reports.ask_gpt_json

    def capture_provider(**kwargs):
        value = real_ask(**kwargs)
        provider_result.append(value)
        return value

    reports.ask_gpt_json = capture_provider
    result = reports.generate_unified_daily_report_sections(1)
    raw = provider_result[0] if provider_result else None
    if not isinstance(raw, dict) or any(
        not isinstance(raw.get(section), str) or len(raw[section].strip()) < 20
        for section in reports.REPORT_V2_SECTIONS
    ):
        raise AssertionError("Provider did not return six complete Report 2.0 sections")
    sections = result["score_source_snapshot"]["report_v2"]["sections"]
    if any(re.search(r"\b(?:market score|technical scores?|total equity|P&L|outlook)\b", text, re.I)
           for text in sections.values()):
        raise AssertionError("English financial source terms remain in Dutch Report 2.0 prose")
    if not any("EUR Cash Builder" in text for text in sections.values()):
        raise AssertionError("Stored plan name was lost from Report 2.0")
    def check_pair_facts(report):
        facts = reports._report_facts(context)
        analysis = report["score_source_snapshot"]["report_v2"]["sections"]["analysis"]
        if reports._report_v2_analysis_claims_contradict(analysis, facts):
            raise AssertionError("Report 2.0 analysis changed a percentage or crossed a pair boundary")
    check_pair_facts(result)
    context["locale"] = "de"
    provider_result.clear()
    german_result = reports.generate_unified_daily_report_sections(1)
    german = german_result["score_source_snapshot"]["report_v2"]["sections"]
    if not provider_result or not isinstance(provider_result[0], dict):
        raise AssertionError("Provider did not return German Report 2.0 prose")
    check_pair_facts(german_result)
    if any(re.search(r"\bWochentag\s*[1-7]\b", text, re.I) for text in german.values()):
        raise AssertionError("German report exposed a stored weekday code")
    if not any("Freitag" in text for text in (german["plan"], german["outlook_v2"])):
        raise AssertionError("German report did not explain the weekly plan with its weekday name")
    context["locale"] = "en"
    provider_result.clear()
    english_result = reports.generate_unified_daily_report_sections(1)
    if not provider_result or not isinstance(provider_result[0], dict):
        raise AssertionError("Provider did not return English Report 2.0 prose")
    check_pair_facts(english_result)
    context["locale"] = "nl"
    for period in ("weekly", "monthly", "quarterly"):
        provider_result.clear()
        period_result = reports.generate_unified_period_report_sections(1, period)
        if not provider_result or not isinstance(provider_result[0], dict):
            raise AssertionError(f"Provider did not return {period} Report 2.0 prose")
        period_snapshot = period_result["score_source_snapshot"]["report_v2"]
        if period_snapshot["period"] != period or any(
            not isinstance(period_snapshot["sections"].get(section), str)
            or len(period_snapshot["sections"][section].strip()) < 20
            for section in reports.REPORT_V2_SECTIONS
        ):
            raise AssertionError(f"Incomplete {period} Report 2.0 sections")
        check_pair_facts(period_result)
        if any(re.search(r"\b(?:market score|technical scores?|total equity|P&L|outlook)\b", text, re.I)
               for text in period_snapshot["sections"].values()):
            raise AssertionError(f"English source terms remain in Dutch {period} report")
        if reports._report_v2_has_unlabeled_component_triplet(
            period_snapshot["sections"]["retrospective"]
        ):
            raise AssertionError(f"Ambiguous component score triplet remains in {period} retrospective")
    print("Report 2.0 real-provider language gate: PASS (NL, DE, EN; day, week, month, quarter)")


if __name__ == "__main__":
    main()
