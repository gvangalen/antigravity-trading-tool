#!/usr/bin/env python3
"""Local public-route regression for budget, valuation and retrieval time."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_bot, _insert_setup, _insert_strategy, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


QUESTIONS = (
    "Ik overweeg €1.000 BTC bij te kopen. Wat kun je uit mijn opgeslagen plan, "
    "de huidige BTC-markt en mijn paper-botportfolio hierover zeggen? Verander niets.",
    "Welke BTC-paperbot en welk budget zag je? Is dat bedrag echt beschikbaar saldo, "
    "en wanneer zijn de gegevens opgehaald?",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("This regression is local-only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        setup_id = _insert_setup(connection, user["id"], "BTC Portfolio Evidence")
        strategy_id = _insert_strategy(
            connection, user["id"], setup_id, "BTC Portfolio Evidence Strategy",
        )
        bot_id = _insert_bot(connection, user["id"], strategy_id, "BTC Evidence Paper Bot")
        connection.execute(text("""
            UPDATE bot_configs SET budget_total_eur = 1000
            WHERE id = :bot_id AND user_id = :user_id
        """), {"bot_id": bot_id, "user_id": user["id"]})

    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    artifact = {"synthetic_local_only": True, "cases": []}
    request = Request(
        f"{args.base_url}/api/portfolio/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(request, timeout=20) as response:
        summary = json.load(response)
    portfolio = summary["data"]
    artifact["shared_portfolio_summary"] = {
        "checks": {
            "budget": portfolio["global"]["total_budget_limit"] == 1000,
            "cash_not_fabricated": portfolio["global"]["cash_balance"] is None,
            "valuation_unavailable": portfolio["valuation_available"] is False,
            "retrieval_date_present": bool(portfolio["read_at"]),
            "valuation_date_absent": summary["as_of"] is None,
            "owner_bot": [bot["name"] for bot in portfolio["bots"]] == ["BTC Evidence Paper Bot"],
        },
    }
    conversation_id = None
    for index, question in enumerate(QUESTIONS):
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=question,
            conversation_id=conversation_id, timeout_seconds=90,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        state = record["runtime_state"]
        trace = (state.get("responses_exchange") or {}).get("tool_trace") or []
        answer = str((state.get("terminal_response") or {}).get("content") or "")
        lower = answer.casefold()
        names = [item.get("name") for item in trace]
        checks = {
            "terminal": observed["status"] == "completed",
            "single_dispatch": observed["dispatch_count"] == observed["attempt_count"] == 1,
            "no_proposal": record["proposal"] is None,
            "portfolio_read": any(name in {"evaluate_portfolio", "get_portfolio_and_exposure"} for name in names),
            "paper_bot_budget": bool(re.search(r"paper[- ]?bot", lower)),
            "budget_amount": bool(re.search(r"1[., ]?000", answer)),
            "budget_not_cash": (
                "budget" in lower
                and bool(re.search(r"\b(?:cash|saldo|kas)\b", lower))
                and bool(re.search(r"\b(?:niet|geen|ontbreekt|ontbreken)\b", lower))
            ),
            "no_internal_field_names": not bool(re.search(
                r"\b(?:as_of|read_at|valuation_available|portfolio_initialized)\b", answer, re.I,
            )),
        }
        if index == 1:
            checks["named_bot"] = "btc evidence paper bot" in lower
            checks["retrieval_date_explained"] = any(term in lower for term in (
                "opgehaald", "gelezen", "opgevraagd", "haalde",
            )) and any(term in lower for term in ("koers", "prijs"))
        artifact["cases"].append({
            "question": question, "run_id": observed["run_id"],
            "status": observed["status"], "tool_names": names,
            "answer": answer, "checks": checks, "pass": all(checks.values()),
        })
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    artifact["pass"] = (
        all(case["pass"] for case in artifact["cases"])
        and all(artifact["shared_portfolio_summary"]["checks"].values())
    )
    Path(args.output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
