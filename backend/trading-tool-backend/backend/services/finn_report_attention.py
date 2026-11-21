"""Pick one bounded, verifiable next question from a frozen report snapshot."""

import re
from math import isfinite
from typing import Any


_PAIR = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}(?:/[A-Z]{2,12})?$")


def _verified_score(value: Any) -> bool:
    return type(value) in {int, float} and isfinite(value) and 0 <= value <= 100


def report_attention(report: dict[str, Any] | None) -> dict[str, str]:
    snapshot = (report or {}).get("score_source_snapshot")
    if not isinstance(snapshot, dict):
        return {}
    assets = snapshot.get("assets")
    if not isinstance(assets, list):
        return {}
    for item in assets:
        if not isinstance(item, dict):
            continue
        pair = str(item.get("pair") or item.get("symbol") or "").strip().upper()
        if not _PAIR.fullmatch(pair):
            continue
        if item.get("score_status") != "available" or not _verified_score(item.get("benchmark_score")):
            return {"attention_kind": "benchmark_unavailable", "attention_pair": pair}
    for item in assets:
        if not isinstance(item, dict):
            continue
        pair = str(item.get("pair") or item.get("symbol") or "").strip().upper()
        if _PAIR.fullmatch(pair) and item.get("score_status") == "available" and _verified_score(item.get("benchmark_score")):
            return {"attention_kind": "benchmark_available", "attention_pair": pair}
    return {}
