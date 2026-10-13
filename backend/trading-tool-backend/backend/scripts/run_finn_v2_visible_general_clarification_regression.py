#!/usr/bin/env python3
"""Check owner-scoped clarification choices through the visible FINN chat route.

Only synthetic local setups are created. No proposal is confirmed or executed.
"""
from __future__ import annotations

import argparse
import json
from uuid import uuid4

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_setup
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json
from backend.scripts.run_finn_v2_visible_draft_correction_regression import _turn
from backend.utils.auth_utils import create_access_token


def run(base_url: str, *, candidate_count: int = 2, mixed_assets: bool = False) -> dict:
    owner = _create_local_user()
    suffix = uuid4().hex[:8]
    asset = "ETH" if mixed_assets else "BTC"
    names = (
        [f"ETH Alpha {suffix}", f"ETH Beta {suffix}", f"ETH Gamma {suffix}",
         "QA vaste ETH vrijdag 2026-10-11"]
        + [f"ETH Keuze {index + 5} {suffix}" for index in range(candidate_count - 4)]
        if mixed_assets else
        [f"BTC Keuze {index + 1} {suffix}" for index in range(candidate_count)]
    )
    with sync_engine.begin() as connection:
        if mixed_assets:
            _insert_setup(connection, owner["id"], f"AAPL First {suffix}", "AAPL")
        setup_ids = [_insert_setup(connection, owner["id"], name, asset) for name in names]
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session, terminal = _turn(
        base_url.rstrip("/"), token, "new",
        f"Wijzig mijn {asset}-setup naar 1D.",
        locale="nl",
    )
    trace = terminal.get("runtime_trace") or {}
    projection = trace.get("terminal_projection") or trace
    clarification = projection.get("clarification") or {}
    choices = clarification.get("choices") or []
    if terminal.get("status") != "clarification_required" or choices != names[:3]:
        raise AssertionError({
            "status": terminal.get("status"),
            "choices": choices,
            "expected": names,
            "response": terminal.get("response"),
            "operation": projection.get("final_operation_id"),
            "supplied_inputs": projection.get("supplied_inputs"),
        })
    if (terminal.get("response") or {}).get("proposal_id"):
        raise AssertionError("ambiguous_setup_created_proposal")
    chosen_index = 3 if candidate_count > 3 else 0
    _, followup = _turn(base_url.rstrip("/"), token, session, names[chosen_index], locale="nl")
    followup_trace = followup.get("runtime_trace") or {}
    followup_projection = followup_trace.get("terminal_projection") or followup_trace
    proposal_id = str((followup.get("response") or {}).get("proposal_id") or "")
    supplied = followup_projection.get("supplied_inputs") or {}
    if (
        followup.get("status") != "completed" or not proposal_id
        or supplied.get("setup_id") != setup_ids[chosen_index]
        or supplied.get("changed_fields") != {"timeframe": "1D"}
    ):
        raise AssertionError({"status": followup.get("status"), "supplied": supplied,
                              "initial_supplied": projection.get("supplied_inputs"),
                              "followup_response": followup.get("response")})
    proposal, http_status = _request_json(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/proposals/{proposal_id}",
        method="GET", headers={"Authorization": f"Bearer {token}"}, body=None, timeout=20,
    )
    if http_status != 200 or proposal.get("status") != "draft" or proposal.get("can_confirm") is False:
        raise AssertionError({"http_status": http_status, "proposal_status": proposal.get("status")})
    if mixed_assets:
        _, correction = _turn(
            base_url.rstrip("/"), token, session,
            "Correctie: ik bedoel een andere ETH-setup met naam "
            "QA niet bestaande ETH setup 999. Verander alleen die naar 4H, bevestig niets.",
            locale="nl",
        )
        old, old_status = _request_json(
            url=f"{base_url.rstrip('/')}/api/assistant/v2/proposals/{proposal_id}",
            method="GET", headers={"Authorization": f"Bearer {token}"}, body=None, timeout=20,
        )
        if (
            correction.get("status") != "clarification_required"
            or (correction.get("response") or {}).get("proposal_id")
            or old_status != 200 or old.get("status") != "cancelled"
        ):
            raise AssertionError({
                "correction_status": correction.get("status"),
                "new_proposal": (correction.get("response") or {}).get("proposal_id"),
                "old_status": old.get("status"),
            })
        correction_choices = (
            (correction.get("runtime_trace") or {}).get("clarification") or {}
        ).get("choices") or []
        if len(correction_choices) < 2 or any("AAPL" in name for name in correction_choices):
            raise AssertionError({"correction_choices": correction_choices})
        _, continued = _turn(
            base_url.rstrip("/"), token, session, names[1], locale="nl",
        )
        continued_trace = continued.get("runtime_trace") or {}
        continued_inputs = (
            (continued_trace.get("action_draft") or {}).get("supplied_inputs") or {}
        )
        if (
            continued.get("status") != "completed"
            or not (continued.get("response") or {}).get("proposal_id")
            or continued_inputs.get("setup_id") != setup_ids[1]
            or continued_inputs.get("changed_fields") != {"timeframe": "4H"}
        ):
            raise AssertionError({
                "continuation_status": continued.get("status"),
                "continuation_inputs": continued_inputs,
            })
        cross_session, cross_first = _turn(
            base_url.rstrip("/"), token, "new",
            "Change my ETH setup to 4H.", locale="en",
        )
        _, cross_choice = _turn(
            base_url.rstrip("/"), token, cross_session,
            f"AAPL First {suffix}", locale="en",
        )
        cross_choices = (
            (cross_choice.get("runtime_trace") or {}).get("clarification") or {}
        ).get("choices") or []
        if (
            cross_first.get("status") != "clarification_required"
            or cross_choice.get("status") != "clarification_required"
            or (cross_choice.get("response") or {}).get("proposal_id")
            or len(cross_choices) < 2
            or any("AAPL" in name for name in cross_choices)
            or not str((cross_choice.get("response") or {}).get("content") or "").startswith("Which")
        ):
            raise AssertionError({"cross_asset_status": cross_choice.get("status"),
                                  "cross_asset_choices": cross_choices,
                                  "cross_asset_response": cross_choice.get("response")})
    return {"status": terminal["status"], "choices": choices,
            "proposal_created": False, "followup_status": followup["status"],
            "followup_target_matches_choice": True, "followup_proposal": True,
            "confirmed": False, "browser_facade": True,
            "unknown_target_rejected": mixed_assets,
            "correction_choice_kept_change": mixed_assets}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--candidate-count", type=int, choices=(2, 7), default=2)
    parser.add_argument("--mixed-assets", action="store_true")
    args = parser.parse_args()
    if args.mixed_assets and args.candidate_count != 7:
        parser.error("--mixed-assets requires --candidate-count 7")
    print(json.dumps(run(
        args.base_url, candidate_count=args.candidate_count, mixed_assets=args.mixed_assets,
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
