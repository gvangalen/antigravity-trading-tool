"""Real-provider, synthetic score-read regression for a dated FOMO follow-up."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import argparse

from openai import AsyncOpenAI

from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_loop import FinnResponsesLoop
from backend.services.finn_v2_verified_turn_context import project_verified_turn


async def run() -> dict:
    now = datetime.now(timezone.utc)
    checked_at = now.isoformat()
    date = now.date().isoformat()
    source_moments = {key: checked_at for key in ("market_score", "macro_score", "technical_score")}
    async def execute(call):
        if call.name == "answer_directly":
            return {"status": "completed", "results": []}
        if call.name == "get_current_asset_scores":
            return {"status": "completed", "results": [{
                "scope": "read_active_asset", "status": "completed", "asset": "ETH",
                "data": {"symbol": "ETH"},
            }, {
                "scope": "read_asset_scores", "status": "completed", "asset": "ETH",
                "source": "daily_scores_and_source_indicators", "freshness": "fresh",
                "as_of": date, "checked_at": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "symbol": "ETH", "as_of": date,
                    "reported_scores": {"market_score": 40, "macro_score": 20, "technical_score": 40},
                    "component_source_status": {key: "fresh" for key in source_moments},
                    "component_source_observed_at": source_moments,
                    "benchmark_score": 33,
                },
            }]}
        return {"status": "unavailable", "reason": "synthetic_scope_not_provided", "results": []}

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        loop = FinnResponsesLoop(client=client, executor=execute)
        first = await loop.run(
            message="Zijn mijn ETH-scores voor Markt, Macro en Technisch nu vers? Noem de waarden.",
            instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
            locale="nl", model_led_coach=True, read_only_turn=True,
        )
        prior = project_verified_turn({
            "answer": first.text, "user_message": "Zijn mijn ETH-scores nu vers?",
            "terminal_status": "completed", "tool_trace": first.tool_trace,
        })
        followups = (
            "Ik krijg FOMO. Kunnen die scores van vandaag een koop nu rechtvaardigen? Denk met me mee, verander niets.",
            "Je zei net dat mijn drie ETH-scores vers waren. Ik wil door FOMO instappen: zijn ze nog actueel en is dat genoeg? Geen actie.",
        )
        turns = [first]
        checks = {
            "first_score_read": any(item.get("name") == "get_current_asset_scores" for item in first.tool_trace),
        }
        for index, message in enumerate(followups, 1):
            followup = await loop.run(
                message=message,
                instructions=FinnResponsesFrontDoor._model_led_instructions("nl"),
                locale="nl", model_led_coach=True, read_only_turn=True,
                verified_turn_context=prior, previous_verified_answer=first.text,
            )
            turns.append(followup)
            lower = followup.text.casefold()
            checks[f"followup_{index}_score_read"] = any(
                item.get("name") == "get_current_asset_scores" for item in followup.tool_trace
            )
            checks[f"followup_{index}_no_false_stale_claim"] = not any(
                phrase in lower for phrase in (
                    "niet vers", "niet actueel", "verouderd", "niet bevestigen dat ze vandaag vers",
                )
            )
            checks[f"followup_{index}_no_trade_instruction"] = not any(
                phrase in lower for phrase in ("koop nu", "koop meteen", "je moet kopen")
            )
        return {
            "synthetic_local_only": True, "model": "gpt-6-luna", "date": date,
            "answers": [turn.text for turn in turns],
            "tool_names": [[item.get("name") for item in turn.tool_trace] for turn in turns],
            "checks": checks, "pass": all(checks.values()),
        }
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pass": result["pass"], "checks": result["checks"],
                      "tool_names": result["tool_names"]}, ensure_ascii=False))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
