#!/usr/bin/env python3
"""Exercise owner-scoped setup collection reads through the public V2 runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import uuid

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, run_gate
from backend.utils.auth_utils import create_access_token


def _create_user(email_prefix: str) -> int:
    with sync_engine.begin() as connection:
        return int(connection.execute(text("""
            INSERT INTO users (email, password_hash, role, is_active, first_name, last_name,
                               subscription_status, created_at, ai_plan, ai_requests_limit_day,
                               ai_requests_used_day, ai_preferences)
            VALUES (:email, 'synthetic-no-login', 'user', TRUE, 'Collection', 'Evidence',
                    'active', NOW(), 'basis', 100, 0, '{"selected_asset":"BTC","locale":"nl"}'::jsonb)
            RETURNING id
        """), {"email": f"{email_prefix}.{uuid.uuid4().hex[:12]}@example.com"}).scalar_one())


def _seed(user_id: int, rows: list[tuple[str, str, str]]) -> None:
    with sync_engine.begin() as connection:
        for name, symbol, timeframe in rows:
            connection.execute(text("""
                INSERT INTO setups (user_id, name, symbol, timeframe, setup_type, created_at)
                VALUES (:user_id, :name, :symbol, :timeframe, 'trade', NOW())
            """), {"user_id": user_id, "name": name, "symbol": symbol, "timeframe": timeframe})


def _terminal(base_url: str, token: str, result: dict) -> dict:
    payload, status = _request_json(
        url=f"{base_url}/api/assistant/v2/runs/{result['run_id']}", method="GET",
        headers={"Authorization": f"Bearer {token}"}, body=None, timeout=10,
    )
    if status != 200:
        raise AssertionError(f"collection_projection_http_{status}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    owner_id = _create_user("finn.collection.owner")
    other_id = _create_user("finn.collection.other")
    namespace = f"collection-{uuid.uuid4().hex[:8]}"
    owner_rows = [
        (f"{namespace} BTC Swing", "BTC", "4H"),
        (f"{namespace} BTC Daily", "BTC", "1D"),
        (f"{namespace} Apple", "AAPL", "1D"),
        (f"{namespace} Microsoft", "MSFT", "1W"),
    ]
    _seed(owner_id, owner_rows)
    _seed(other_id, [(f"{namespace} Private BTC", "BTC", "1H")])
    token = create_access_token({"sub": str(owner_id), "role": "user"})
    checks = []
    try:
        for prompt, expected, excluded in (
            ("Welke BTC setups heb ik?", [row[0] for row in owner_rows[:2]], [owner_rows[2][0], f"{namespace} Private BTC"]),
            ("Welke setups heb ik voor al mijn assets?", [row[0] for row in owner_rows], [f"{namespace} Private BTC"]),
            ("Welke AAPL setup heb ik?", [owner_rows[2][0]], [owner_rows[0][0], owner_rows[3][0]]),
        ):
            gate = run_gate(base_url=args.base_url, bearer_token=token, message=prompt, timeout_seconds=60)
            terminal = _terminal(args.base_url, token, gate)
            projection = dict((terminal.get("runtime_trace") or {}))
            response = dict(terminal.get("response") or projection.get("response") or {})
            visible = " ".join(str(response.get(key) or "") for key in ("content", "direct_answer", "main_observation"))
            collection = dict(projection.get("canonical_target_collection") or {})
            passed = all(name in visible for name in expected) and all(name not in visible for name in excluded)
            checks.append({
                "prompt": prompt,
                "run_id": gate["run_id"],
                "target_mode": "collection" if collection else "single",
                "result_count": collection.get("result_count"),
                "returned_names": [item.get("display_name") for item in collection.get("items") or []],
                "polling_sse_parity": gate.get("polling_sse_contract_projection"),
                "dispatch_count": gate.get("dispatch_count"),
                "attempt_count": gate.get("attempt_count"),
                "passed": passed,
            })
        artifact = {
            "artifact_version": "finn_v2.collection_evidence.v1",
            "synthetic_local_only": True,
            "namespace": namespace,
            "checks": checks,
            "passed": all(item["passed"] for item in checks),
            "cross_user_leaks": 0 if all(item["passed"] for item in checks) else None,
        }
    finally:
        with sync_engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE id IN (:owner_id, :other_id)"), {"owner_id": owner_id, "other_id": other_id})
    output = Path(args.output)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "passed": artifact["passed"]}, sort_keys=True))
    if not artifact["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
