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


def run(base_url: str) -> dict:
    owner = _create_local_user()
    suffix = uuid4().hex[:8]
    names = [f"BTC Keuze Alpha {suffix}", f"BTC Keuze Beta {suffix}"]
    with sync_engine.begin() as connection:
        setup_ids = [_insert_setup(connection, owner["id"], name, "BTC") for name in names]
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session, terminal = _turn(
        base_url.rstrip("/"), token, "new",
        "Wijzig mijn BTC-setup naar 1D.",
        locale="nl",
    )
    trace = terminal.get("runtime_trace") or {}
    projection = trace.get("terminal_projection") or trace
    clarification = projection.get("clarification") or {}
    choices = clarification.get("choices") or []
    if terminal.get("status") != "clarification_required" or set(choices) != set(names):
        raise AssertionError({
            "status": terminal.get("status"),
            "choices": choices,
            "expected": names,
        })
    if (terminal.get("response") or {}).get("proposal_id"):
        raise AssertionError("ambiguous_setup_created_proposal")
    _, followup = _turn(base_url.rstrip("/"), token, session, names[0], locale="nl")
    followup_trace = followup.get("runtime_trace") or {}
    followup_projection = followup_trace.get("terminal_projection") or followup_trace
    proposal_id = str((followup.get("response") or {}).get("proposal_id") or "")
    supplied = followup_projection.get("supplied_inputs") or {}
    if (
        followup.get("status") != "completed" or not proposal_id
        or supplied.get("setup_id") != setup_ids[0]
        or supplied.get("changed_fields") != {"timeframe": "1D"}
    ):
        raise AssertionError({"status": followup.get("status"), "supplied": supplied})
    proposal, http_status = _request_json(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/proposals/{proposal_id}",
        method="GET", headers={"Authorization": f"Bearer {token}"}, body=None, timeout=20,
    )
    if http_status != 200 or proposal.get("status") != "draft" or proposal.get("can_confirm") is False:
        raise AssertionError({"http_status": http_status, "proposal_status": proposal.get("status")})
    return {"status": terminal["status"], "choices": choices,
            "proposal_created": False, "followup_status": followup["status"],
            "followup_target_matches_choice": True, "followup_proposal": True,
            "confirmed": False, "browser_facade": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
