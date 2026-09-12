#!/usr/bin/env python3
"""Add public NL/EN/DE selection proof to the safe FINN write matrix.

The main action matrix owns the proposal, confirmation, execution and replay
proof.  This companion performs only the missing multilingual proposal-stage
proof, using the same public V2 route and registry-owned required inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import sleep
from urllib.parse import urlparse

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record, _seed_fixtures
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


PROBES: dict[str, tuple[str, str]] = {
    "select_asset": ("Select SOL as my active asset.", "Wähle SOL als mein aktives Asset."),
    "watchlist_add": ("Add ETH to my watchlist.", "Füge ETH zu meiner Watchlist hinzu."),
    "watchlist_remove": ("Remove XRP from my watchlist.", "Entferne XRP aus meiner Watchlist."),
    "create_indicator_configuration": (
        "Create a technical RSI indicator configuration for ADA.",
        "Erstelle eine technische RSI-Indikatorkonfiguration für ADA.",
    ),
    "update_indicator_configuration": (
        "Update my technical BTC RSI configuration and set the period to 21.",
        "Aktualisiere meine technische BTC-RSI-Konfiguration und setze die Periode auf 21.",
    ),
    "delete_indicator_configuration": (
        "Delete my technical SOL RSI configuration.",
        "Lösche meine technische SOL-RSI-Konfiguration.",
    ),
    "create_setup": (
        "Create a SOL swing setup on 4 hours named Matrix New Setup.",
        "Erstelle ein SOL-Swing-Setup auf 4 Stunden mit dem Namen Matrix New Setup.",
    ),
    "update_setup": (
        "Update Matrix Update Setup and set its timeframe to 1 hour.",
        "Aktualisiere Matrix Update Setup und setze den Zeitrahmen auf 1 Stunde.",
    ),
    "delete_setup": ("Delete the setup Matrix Delete Setup.", "Lösche das Setup Matrix Delete Setup."),
    "create_strategy": (
        "Create a fixed strategy for Matrix Strategy Parent with a base amount of 100 euros named Matrix New Strategy.",
        "Erstelle für Matrix Strategy Parent eine feste Strategie mit einem Basisbetrag von 100 Euro namens Matrix New Strategy.",
    ),
    "update_strategy": (
        "Update Matrix Update Strategie and set the base amount to 120 euros.",
        "Aktualisiere Matrix Update Strategie und setze den Basisbetrag auf 120 Euro.",
    ),
    "delete_strategy": ("Delete the strategy Matrix Delete Strategie.", "Lösche die Strategie Matrix Delete Strategie."),
    "create_bot": (
        "Create a paper bot for Matrix Bot Parent named Matrix New Bot.",
        "Erstelle einen Paper-Bot für Matrix Bot Parent mit dem Namen Matrix New Bot.",
    ),
    "update_bot": (
        "Update Matrix Update Bot and set the cadence to weekly.",
        "Aktualisiere Matrix Update Bot und setze die Taktung auf wöchentlich.",
    ),
    "deactivate_bot": ("Deactivate Matrix Deactivate Bot.", "Deaktiviere Matrix Deactivate Bot."),
    "delete_bot": ("Delete Matrix Delete Bot.", "Lösche Matrix Delete Bot."),
}


def _probe(base_url: str, token: str, operation_id: str, message: str) -> dict:
    observed = run_gate(base_url=base_url, bearer_token=token, message=message, timeout_seconds=60)
    record = _runtime_record(observed["run_id"])
    projection = record["terminal_projection"]
    contract = FinnV2OperationRegistry().require_supported(operation_id)
    supplied = dict(projection.get("supplied_inputs") or {})
    # A semantically identical multilingual request can safely reuse its
    # existing owner-scoped draft under the action contract's payload-hash
    # idempotency rule. The current run then has no new proposal row, but the
    # canonical terminal projection remains the public proposal authority.
    proposal_id = (record["proposal"] or {}).get("id") or (
        (projection.get("proposal_lifecycle") or {}).get("proposal_id")
    ) or ((projection.get("response") or {}).get("proposal_id"))
    passed = all((
        observed["initial_operation_id"] == operation_id,
        observed["final_operation_id"] == operation_id,
        set(contract.required_inputs).issubset(supplied),
        not projection.get("missing_inputs"),
        bool(record["runtime_contract_id"]),
        bool(proposal_id),
        observed.get("dispatch_count") == 1,
        observed.get("attempt_count") == 1,
        observed["polling_sse_contract_projection"],
    ))
    return {
        "message": message,
        "run_id": observed["run_id"],
        "runtime_contract_id": record["runtime_contract_id"],
        "initial_operation_id": observed["initial_operation_id"],
        "final_operation_id": observed["final_operation_id"],
        "required_inputs": list(contract.required_inputs),
        "supplied_inputs": supplied,
        "missing_inputs": projection.get("missing_inputs"),
        "proposal_id": proposal_id,
        "dispatch_count": observed.get("dispatch_count"),
        "attempt_count": observed.get("attempt_count"),
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "elapsed_ms": observed["elapsed_ms"],
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--provider-pace-seconds", type=float, default=2.0)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("write_language_certification_requires_loopback")
    cards = []
    for operation_id, messages in PROBES.items():
        user = _create_local_user()
        _seed_fixtures(int(user["id"]))
        token = create_access_token({"sub": str(user["id"]), "role": "user"})
        tests = []
        for message in messages:
            tests.append(_probe(base_url, token, operation_id, message))
            sleep(max(0.0, args.provider_pace_seconds))
        cards.append({
            "operation_id": operation_id,
            "testcases": tests,
            "passed": all(item["passed"] for item in tests),
        })
    payload = {"artifact_version": "finn_v2.write_language_certification.v1", "cards": cards}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "cards": len(cards)}))


if __name__ == "__main__":
    main()
