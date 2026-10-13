#!/usr/bin/env python3
"""Exercise German draft creation through the authenticated web/worker route.

Uses a synthetic local owner. The proposals are never confirmed or executed.
"""
from __future__ import annotations

import argparse
import json

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user
from backend.scripts.run_finn_v2_visible_draft_correction_regression import _fields, _turn
from backend.utils.auth_utils import create_access_token


def _expect_proposal(terminal: dict, expected_fields: dict) -> None:
    if terminal.get("status") != "completed" or not (terminal.get("response") or {}).get("proposal_id"):
        raise AssertionError("localized_draft_proposal_missing")
    fields = _fields(terminal)
    if any(fields.get(key) != value for key, value in expected_fields.items()):
        raise AssertionError(f"localized_draft_fields_mismatch_{fields}")
    answer = str((terminal.get("response") or {}).get("content") or "")
    if not answer.startswith("Ich kann") or "Er is nog niets" in answer:
        raise AssertionError("localized_draft_answer_not_german")


def run(base_url: str) -> dict:
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    _, indicator = _turn(
        base_url, token, "new", "Füge ADX als technischen Indikator für ETH hinzu.", locale="de",
    )
    _expect_proposal(indicator, {"asset": "ETH", "category": "technical", "indicator": "adx"})

    prefix = (
        "Erstelle ein wöchentliches BTC-DCA-Setup im 1D-Zeitrahmen, "
        "Name QA BTC Deutsch Lokal 13 Oktober, fester Betrag 10 Euro pro Ausführung"
    )
    expected_dca = {
        "name": "QA BTC Deutsch Lokal 13 Oktober", "symbol": "BTC", "timeframe": "1D",
        "setup_type": "dca", "dca_frequency": "weekly", "dca_day": "friday",
        "dca_amount_mode": "fixed", "base_amount": 10.0,
    }
    _, complete = _turn(
        base_url, token, "new",
        prefix + ", immer freitags. Zeige nur den Entwurf; bestätige nichts.", locale="de",
    )
    _expect_proposal(complete, expected_dca)

    session, pending = _turn(
        base_url, token, "new", prefix + ". Zeige nur den Entwurf; bestätige nichts.", locale="de",
    )
    if pending.get("status") != "clarification_required" or (
        (pending.get("runtime_trace") or {}).get("missing_inputs") != ["dca_day"]
    ):
        raise AssertionError("localized_draft_missing_day_not_requested")
    _, completed = _turn(base_url, token, session, "Freitag.", locale="de")
    _expect_proposal(completed, expected_dca)
    return {"checks": 3, "indicator_draft": True, "complete_dca_draft": True,
            "two_turn_dca_draft": True, "confirmed": False, "browser_facade": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
