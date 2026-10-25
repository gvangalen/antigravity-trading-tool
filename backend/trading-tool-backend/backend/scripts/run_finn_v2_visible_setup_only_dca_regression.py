#!/usr/bin/env python3
"""Exercise setup-only DCA drafts through the same local stream facade as web chat.

Uses synthetic local users and real Luna/Responses. An optional local-only
confirmation probe verifies that setup-only creates no strategy.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _proposal_lifecycle
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json
from backend.scripts.run_finn_v2_visible_guided_dca_regression import _turn, _projection
from backend.utils.auth_utils import create_access_token


def _case(base_url: str, turns: tuple[str, ...], *, expect_bounds: bool,
          confirm_local: bool = False) -> dict:
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session_id = "new"
    records = []
    for question in turns:
        session_id, terminal = _turn(base_url, token, session_id, question)
        projection = _projection(terminal)
        records.append({
            "status": terminal.get("status"),
            "supplied": projection.get("supplied_inputs") or {},
            "missing": projection.get("missing_inputs") or [],
            "proposal_id": (terminal.get("response") or {}).get("proposal_id"),
        })
    final = records[-1]
    supplied = final["supplied"]
    if final["status"] != "completed" or not final["proposal_id"]:
        raise AssertionError(f"setup_only_proposal_missing:{records}")
    if supplied.get("plan_scope") != "setup_only":
        raise AssertionError(f"setup_only_scope_missing:{records}")
    if supplied.get("dca_frequency") != "weekly" or supplied.get("dca_day") != "friday":
        raise AssertionError(f"setup_only_cadence_lost:{records}")
    if any(key in supplied for key in ("base_amount", "dca_amount_mode", "low_threshold", "high_threshold")):
        raise AssertionError(f"setup_only_strategy_fields_leaked:{records}")
    bounds = (supplied.get("min_benchmark_score"), supplied.get("max_benchmark_score"))
    if bounds != ((26, 45) if expect_bounds else (None, None)):
        raise AssertionError(f"setup_only_wrong_eligibility:{records}")
    result = {"turns": len(records), "proposal": True, "scope": supplied["plan_scope"],
              "bounds": bounds, "confirmed": False}
    if confirm_local:
        proposal, proposal_status = _request_json(
            url=f"{base_url}/api/assistant/v2/proposals/{final['proposal_id']}",
            method="GET", headers={"Authorization": f"Bearer {token}"}, body=None,
            timeout=20,
        )
        if proposal_status != 200:
            raise AssertionError(f"setup_only_proposal_read_failed:{proposal_status}")
        with sync_engine.connect() as connection:
            before = connection.execute(text(
                "SELECT COUNT(*) FROM setups WHERE user_id = :owner_id"
            ), {"owner_id": owner["id"]}).scalar_one()
            payload_hash = connection.execute(text(
                "SELECT payload_hash FROM finn_v2_proposals WHERE id = :proposal_id"
            ), {"proposal_id": final["proposal_id"]}).scalar_one()
        other = _create_local_user()
        other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
        lifecycle = _proposal_lifecycle(base_url, token, other_token, {
            "id": final["proposal_id"], "payload_hash": payload_hash,
        })
        with sync_engine.connect() as connection:
            saved = connection.execute(text(
                "SELECT id, dca_frequency, dca_day, min_benchmark_score, max_benchmark_score "
                "FROM setups WHERE user_id = :owner_id ORDER BY id DESC LIMIT 1"
            ), {"owner_id": owner["id"]}).mappings().one_or_none()
            strategies = connection.execute(text(
                "SELECT COUNT(*) FROM strategies WHERE user_id = :owner_id"
            ), {"owner_id": owner["id"]}).scalar_one()
        if before != 0 or not saved or strategies != 0:
            raise AssertionError(f"setup_only_write_shape:{before}:{saved}:{strategies}")
        if (saved["dca_frequency"], saved["dca_day"], saved["min_benchmark_score"],
                saved["max_benchmark_score"]) != ("weekly", "5", *bounds):
            raise AssertionError(f"setup_only_saved_fields:{saved}")
        if not (lifecycle["cross_user_rejected"] and lifecycle["confirmed"]
                and lifecycle["execution_result"] == "succeeded"
                and lifecycle["idempotency_result"] == "already_executed"):
            raise AssertionError(f"setup_only_lifecycle:{lifecycle}")
        result.update({"confirmed": True, "setup_saved": True, "strategy_count": 0,
                       "cross_user_rejected": True, "idempotent": True})
    return result


def _scope_revision_case(base_url: str) -> dict:
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session_id, first = _turn(
        base_url, token, "new",
        "Maak alleen een BTC DCA-setup met naam QA BTC Staffel Later 2510, "
        "primair timeframe 1D, wekelijks op vrijdag. Als enige setupvoorwaarde "
        "totale benchmarkscore 26 tot 45. De Smart-DCA-staffel van 40 tot 70 "
        "bepaal ik later in de strategie.",
    )
    first_id = (first.get("response") or {}).get("proposal_id")
    if not first_id:
        raise AssertionError("scope_revision_initial_proposal_missing")
    first_inputs = _projection(first).get("supplied_inputs") or {}
    if (first_inputs.get("min_benchmark_score") != 26
            or first_inputs.get("max_benchmark_score") != 45):
        raise AssertionError(f"scope_revision_initial_bounds_missing:{first_inputs}")
    _, second = _turn(
        base_url, token, session_id,
        "Ik verander dit open concept: maak er een volledig BTC DCA-plan van "
        "met een vast bedrag van €100 per week op vrijdag. Behoud de naam "
        "QA BTC Staffel Later 2510 en geen setupscorefilter. Toon de nieuwe "
        "conceptkaart; bevestig niets.",
    )
    second_id = (second.get("response") or {}).get("proposal_id")
    supplied = _projection(second).get("supplied_inputs") or {}
    expected = {
        "name": "QA BTC Staffel Later 2510", "symbol": "BTC", "timeframe": "1D",
        "setup_type": "dca", "plan_scope": "setup_and_strategy",
        "dca_frequency": "weekly", "dca_day": "friday",
        "dca_amount_mode": "fixed", "base_amount": 100,
    }
    if second.get("status") != "completed" or not second_id or second_id == first_id:
        raise AssertionError(f"scope_revision_replacement_missing:{second.get('error_code')}:{supplied}")
    if any(supplied.get(key) != value for key, value in expected.items()):
        raise AssertionError(f"scope_revision_fields:{supplied}")
    if any(key in supplied for key in ("score_source", "low_threshold", "high_threshold",
                                       "min_benchmark_score", "max_benchmark_score")):
        raise AssertionError(f"scope_revision_old_staffel_leaked:{supplied}")
    return {"turns": 2, "proposal_replaced": True, "confirmed": False}


def run(base_url: str, *, confirm_local: bool = False) -> dict:
    base_url = base_url.rstrip("/")
    direct = _case(base_url, (
        "Maak alleen een BTC DCA-setup met naam QA BTC Vrijdag, primair timeframe 1D, "
        "wekelijks op vrijdag, als enige koopvoorwaarde totale benchmarkscore 26 tot 45. "
        "Geen strategie of bedrag nu.",
    ), expect_bounds=True, confirm_local=confirm_local)
    continued = _case(base_url, (
        "Maak een BTC DCA-setup met naam QA BTC Vrijdag, primair timeframe 1D, "
        "wekelijks op vrijdag, als koopvoorwaarde totale benchmarkscore 26 tot 45.",
        "Dat bepaal ik later in de strategie.",
    ), expect_bounds=True)
    future_staffel = _case(base_url, (
        "Maak alleen een BTC DCA-setup met naam QA BTC Vrijdag, primair timeframe 1D, "
        "wekelijks op vrijdag. De Smart DCA-staffel van 40 tot 70 bepaal ik later "
        "in de strategie; geen setupscorefilter.",
    ), expect_bounds=False)
    revised = _scope_revision_case(base_url)
    return {"direct": direct, "continued": continued,
            "future_staffel": future_staffel, "scope_revision": revised}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--confirm-local", action="store_true")
    args = parser.parse_args()
    if args.confirm_local and not args.base_url.startswith("http://127.0.0.1:"):
        raise SystemExit("confirmation is restricted to the local runtime")
    print(json.dumps(run(args.base_url, confirm_local=args.confirm_local), ensure_ascii=False))


if __name__ == "__main__":
    main()
