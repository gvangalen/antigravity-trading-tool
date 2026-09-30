"""Non-sealed real-provider development cases for saved-plan read scope."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from backend.services.finn_v2_responses_tool_relevance import FinnResponsesToolRelevanceGuard
from backend.utils import openai_client


CASES = (
    ("Welke BTC-setups staan er op Mijn Plan? Noem de namen.", "", "inventory", "", ""),
    ("Ik heb BTC-plannen in Mijn Plan. Kun je ze allemaal opsommen?", "", "inventory", "", ""),
    ("Noem alle drie mijn BTC-setups bij naam.", "", "inventory", "", ""),
    ("Bij welke van die drie staat een entrybevestiging?", "saved_setup_collection", "confirmation_inventory", "", ""),
    ("Is er bij een van die plannen een bevestigde instapvoorwaarde opgeslagen?", "saved_setup_collection", "confirmation_inventory", "", ""),
    ("Welke van mijn BTC-setups heeft een entrytrigger?", "", "confirmation_inventory", "", ""),
    ("Ik voel FOMO. Mag ik mijn BTC-DCA-regel zomaar op AAPL toepassen?", "", "cross_asset_scope", "BTC", "AAPL"),
    ("Geldt mijn BTC-DCA-regel ook voor Apple/AAPL?", "", "cross_asset_scope", "BTC", "AAPL"),
    ("Mijn BTC-DCA loopt maandag. Zou ik dat plan ook voor Apple mogen gebruiken?", "", "cross_asset_scope", "BTC", "AAPL"),
    ("Welke setup is voor mijn BTC-plan actief?", "", "none", "", ""),
    ("Ik voel FOMO omdat de koers stijgt. Hoe rem ik mezelf af?", "", "none", "", ""),
    ("Maak drie BTC-setups voor me.", "", "none", "", ""),
    ("Ik wil mijn stop-loss weghalen. Ik vraag om coaching, niet om een wijziging.", "", "none", "", ""),
    ("Stel dat ik acht impulsieve trades deed. Welk patroon zie je?", "", "none", "", ""),
)


async def run() -> list[dict]:
    client = openai_client.async_client
    if client is None:
        raise RuntimeError("provider_unconfigured")
    guard = FinnResponsesToolRelevanceGuard(client)
    rows = []
    for message, previous_kind, kind, source, target in CASES:
        actual = await guard.saved_plan_query_kind(
            message=message, previous_kind=previous_kind,
            previous_answer=("Ik zie drie BTC-setups." if previous_kind else ""),
        )
        actual = actual or {}
        passed = (actual.get("kind") == kind and (
            kind != "cross_asset_scope" or (
                actual.get("source_asset", "").upper() == source
                and actual.get("target_asset", "").upper() == target
            )
        ))
        rows.append({
            "message": message, "previous_kind": previous_kind,
            "expected": {"kind": kind, "source_asset": source, "target_asset": target},
            "actual": actual, "passed": passed,
        })
        await asyncio.sleep(0.3)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = asyncio.run(run())
    report = {"dataset": "public_saved_plan_query_development", "total": len(rows),
              "passed": sum(row["passed"] for row in rows), "cases": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "total": report["total"],
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
