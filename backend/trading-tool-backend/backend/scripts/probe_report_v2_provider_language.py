"""Synthetic, non-user Report 2.0 language probe against the real provider.

Run only in the manually dispatched CI job with its protected OpenAI secret.
No model output or credentials are printed.
"""

from __future__ import annotations

import asyncio
import os
import re

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
        "assets": [{
            "symbol": "BTC", "pair": "BTC/EUR",
            "setups": [{"id": 1, "name": "Cash Builder", "setup_type": "dca",
                        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": 5}],
            "strategies": [{"id": 2, "name": "BTC DCA", "setup_id": 1,
                            "execution_mode": "fixed", "base_amount": 100}],
            "bots": [],
            "benchmark": {"source_status": "missing", "reported_scores": {},
                          "component_source_status": {}},
            "market_snapshot": {"source_status": "fresh", "change_24h": 0.5},
        }],
    }
    reports._load_context = lambda _user_id: asyncio.sleep(0, result=context)
    provider_result = {}
    real_ask = reports.ask_gpt_json

    def capture_provider(**kwargs):
        provider_result["value"] = real_ask(**kwargs)
        return provider_result["value"]

    reports.ask_gpt_json = capture_provider
    result = reports.generate_unified_daily_report_sections(1)
    raw = provider_result.get("value")
    if not isinstance(raw, dict) or any(
        not isinstance(raw.get(section), str) or len(raw[section].strip()) < 20
        for section in reports.REPORT_V2_SECTIONS
    ):
        raise AssertionError("Provider did not return six complete Report 2.0 sections")
    sections = result["score_source_snapshot"]["report_v2"]["sections"]
    if any(re.search(r"\b(?:market score|technical scores?|total equity|P&L|outlook)\b", text, re.I)
           for text in sections.values()):
        raise AssertionError("English financial source terms remain in Dutch Report 2.0 prose")
    if not any("Cash Builder" in text for text in sections.values()):
        raise AssertionError("Stored plan name was lost from Report 2.0")
    context["locale"] = "de"
    provider_result.clear()
    german_result = reports.generate_unified_daily_report_sections(1)
    german = german_result["score_source_snapshot"]["report_v2"]["sections"]
    if not isinstance(provider_result.get("value"), dict):
        raise AssertionError("Provider did not return German Report 2.0 prose")
    if any(re.search(r"\bWochentag\s*[1-7]\b", text, re.I) for text in german.values()):
        raise AssertionError("German report exposed a stored weekday code")
    if not any("Freitag" in text for text in (german["plan"], german["outlook_v2"])):
        raise AssertionError("German report did not explain the weekly plan with its weekday name")
    print("Report 2.0 real-provider language gate: PASS (NL and DE)")


if __name__ == "__main__":
    main()
