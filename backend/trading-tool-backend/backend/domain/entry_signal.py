"""Versioned, pair-bound entry evidence. This module never places an order."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import re
from typing import Any


def entry_signal_capabilities() -> dict[str, Any]:
    """Model-facing executable facts; no prewritten FINN coach answer."""
    return {
        "version": 1,
        "trade_only": True,
        "market_binding": "saved_setup_exact_spot_pair",
        "timeframe": "1D_closed_candles",
        "event": "close_crosses_reference",
        "directions": ["above", "below"],
        "references": [
            {"kind": "sma", "period_min": 2, "period_max": 219},
            {"kind": "trendline", "anchors": "two dated price points in pair quote currency"},
        ],
        "execution": "additional gate on confirmed absolute entry, stop, targets and Score 2.0 setup conditions; Paper only",
        "unavailable_evidence": "hold without a new entry",
    }


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("entry_signal_invalid_number")
    return float(value)


def _moment(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("entry_signal_invalid_moment") from exc
    if result.tzinfo is None:
        raise ValueError("entry_signal_moment_requires_timezone")
    return result.astimezone(timezone.utc)


def validate_entry_signal(value: Any) -> dict[str, Any]:
    """Accept only an explicit closed-candle crossing over a typed reference."""
    if not isinstance(value, dict) or set(value) != {"version", "event", "direction", "timeframe", "reference"}:
        raise ValueError("entry_signal_invalid_shape")
    if value["version"] != 1 or value["event"] != "close_crosses_reference":
        raise ValueError("entry_signal_unsupported_event")
    if value["direction"] not in {"above", "below"} or value["timeframe"] != "1D":
        raise ValueError("entry_signal_unsupported_direction_or_timeframe")
    reference = value["reference"]
    if not isinstance(reference, dict):
        raise ValueError("entry_signal_invalid_reference")
    if reference.get("kind") == "sma" and set(reference) == {"kind", "period"}:
        period = reference["period"]
        # The exact-pair history bootstrap supports at most 220 closed days.
        # A crossing needs one more candle than the moving-average period.
        if type(period) is not int or not 2 <= period <= 219:
            raise ValueError("entry_signal_invalid_period")
        canonical_reference = {"kind": "sma", "period": period}
    elif reference.get("kind") == "trendline" and set(reference) == {"kind", "anchors"}:
        anchors = reference["anchors"]
        if not isinstance(anchors, list) or len(anchors) != 2:
            raise ValueError("entry_signal_invalid_anchors")
        if any(not isinstance(point, dict) or set(point) != {"at", "price"} for point in anchors):
            raise ValueError("entry_signal_invalid_anchors")
        first, second = (_moment(point["at"]) for point in anchors)
        if first >= second:
            raise ValueError("entry_signal_invalid_anchors")
        canonical_reference = {"kind": "trendline", "anchors": [
            {"at": moment.isoformat(), "price": _number(point["price"])}
            for moment, point in zip((first, second), anchors)
        ]}
    else:
        raise ValueError("entry_signal_invalid_reference")
    return {"version": 1, "event": "close_crosses_reference",
            "direction": value["direction"], "timeframe": "1D",
            "reference": canonical_reference}


def explicit_entry_signal_from_text(message: str) -> dict[str, Any] | None:
    """Extract only a complete, explicit generic crossing rule from user text.

    This is an input parser, not a coach response or a guess about a signal.
    Unspecified direction, candle closure, reference or trendline anchors must
    remain unresolved instead of becoming an ordinary fixed-price strategy.
    """
    text = str(message or "")
    if not (re.search(r"\b(?:afgesloten\s+(?:1D\s+)?[A-Z0-9]{2,10}/[A-Z0-9]{2,10}[- ]slotkoers|"
                      r"afgesloten\s+(?:1D[- ]?)?(?:dag)?slotkoers|"
                      r"afgesloten\s+dagkoers|afgesloten\s+(?:1D[- ]?)?(?:dagkaars|dagcandle)|"
                      r"dag(?:slot)?koers|daily\s+close|closed\s+daily\s+candle|"
                      r"tagesschlusskurs)\b", text, re.I)
            and re.search(r"\b(?:kruis\w*|cross\w*|kreuz\w*)\b", text, re.I)):
        return None
    above = bool(re.search(r"\b(?:opwaartse\s+kruising|upward\s+cross(?:ing)?|"
                           r"kruis\w*\s+opwaarts|"
                           r"van\s+onder\s+naar\s+boven|from\s+below\s+to\s+above|"
                           r"von\s+unten\s+nach\s+oben|kruis\w*\s+boven|"
                           r"boven\s+(?:de\s+|het\s+)?(?:sma|ma)\s*\d+\s+kruis\w*|"
                           r"cross\w*\s+above|kreuz\w*\s+(?:über|ueber))\b", text, re.I))
    below = bool(re.search(r"\b(?:neerwaartse\s+kruising|downward\s+cross(?:ing)?|"
                           r"kruis\w*\s+neerwaarts|"
                           r"van\s+boven\s+naar\s+onder|from\s+above\s+to\s+below|"
                           r"von\s+oben\s+nach\s+unten|kruis\w*\s+onder|"
                           r"onder\s+(?:de\s+|het\s+)?(?:sma|ma)\s*\d+\s+kruis\w*|"
                           r"cross\w*\s+below|kreuz\w*\s+unter)\b", text, re.I))
    if above == below:
        return None
    sma = re.findall(
        r"\b(?:sma|ma|moving\s+average)\s*(?:over\s+)?[- ]?(\d{1,3})\b",
        text, re.I,
    )
    line = bool(re.search(r"\b(?:trendlijn|trendline|trendlinie)\b", text, re.I))
    if bool(sma) == line or len(set(sma)) > 1:
        return None
    if sma:
        reference = {"kind": "sma", "period": int(sma[0])}
    else:
        # A clock time without a timezone cannot be mapped safely to a candle.
        if re.search(r"\b\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?\b(?!\s*(?:UTC|Z)\b)", text, re.I):
            return None
        anchors = re.findall(
            r"\b(\d{4}-\d{2}-\d{2})"
            r"(?:\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:UTC|Z))?\s*"
            r"(?:(?:op|at|bei|:|=)\s*)?(?:€|\$|EUR|USD|USDT)?\s*"
            r"(\d+(?:[.,]\d+)?)\b", text, re.I,
        )
        if len(anchors) != 2:
            return None
        def anchor_price(raw: str) -> float:
            if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
                return float(raw.replace(".", "").replace(",", ""))
            return float(raw.replace(",", "."))
        reference = {"kind": "trendline", "anchors": [
            {"at": f"{day}T{clock if clock else '00:00'}Z", "price": anchor_price(price)}
            for day, clock, price in anchors
        ]}
    try:
        return validate_entry_signal({
            "version": 1, "event": "close_crosses_reference",
            "direction": "above" if above else "below", "timeframe": "1D",
            "reference": reference,
        })
    except ValueError:
        return None


def evaluate_entry_signal(
    rule: dict[str, Any], candles: list[dict[str, Any]], *, market_id: int,
    now: datetime, max_closed_age_hours: int = 72,
) -> dict[str, Any]:
    """Evaluate two completed bars; missing/stale evidence is never a signal.

    Candles are direct-market 1D bars with ``at`` and ``close``. The caller
    supplies the saved setup's market ID, not the current Analyse selection.
    """
    rule = validate_entry_signal(rule)
    now = _moment(now.isoformat())
    if type(market_id) is not int or market_id <= 0:
        return {"status": "market_unavailable"}
    required = (rule["reference"].get("period", 2) + 1
                if rule["reference"]["kind"] == "sma" else 2)
    if len(candles) < required:
        return {"status": "insufficient_closed_candles", "required": required,
                "available": len(candles)}
    recent = candles[-required:]
    try:
        points = [(_moment(item["at"]), _number(item["close"])) for item in recent]
    except (KeyError, TypeError, ValueError):
        return {"status": "invalid_candle_evidence"}
    if any(a[0] >= b[0] for a, b in zip(points, points[1:])):
        return {"status": "invalid_candle_evidence"}
    if any((b[0].date() - a[0].date()).days != 1 for a, b in zip(points, points[1:])):
        return {"status": "missing_closed_candle_days"}
    previous_at, previous_close = points[-2]
    current_at, current_close = points[-1]
    if (current_at >= now or current_at.date() != now.date() - timedelta(days=1)
            or (now - current_at).total_seconds() > max_closed_age_hours * 3600):
        return {"status": "closed_candle_stale_or_unconfirmed"}
    reference = rule["reference"]
    if reference["kind"] == "sma":
        period = reference["period"]
        previous_reference = sum(close for _, close in points[-period-1:-1]) / period
        current_reference = sum(close for _, close in points[-period:]) / period
    else:
        first, second = reference["anchors"]
        first_at, second_at = _moment(first["at"]), _moment(second["at"])
        if current_at < second_at or previous_at < second_at:
            return {"status": "trendline_anchors_not_completed"}
        slope = (second["price"] - first["price"]) / (second_at - first_at).total_seconds()
        previous_reference = first["price"] + slope * (previous_at - first_at).total_seconds()
        current_reference = first["price"] + slope * (current_at - first_at).total_seconds()
        if min(previous_reference, current_reference) <= 0:
            return {"status": "invalid_reference_value"}
    crossed = (previous_close <= previous_reference and current_close > current_reference
               if rule["direction"] == "above" else
               previous_close >= previous_reference and current_close < current_reference)
    # Bind a Paper decision to the exact candle evidence, including the SMA
    # lookback. A provider correction must require a fresh decision.
    identity = json.dumps({"market_id": market_id, "rule": rule,
                           "candles": [(at.isoformat(), close) for at, close in points]},
                          sort_keys=True, separators=(",", ":"))
    return {"status": "triggered" if crossed else "not_triggered",
            "market_id": market_id, "rule": rule,
            "closed_at": current_at.isoformat(),
            "previous_close": previous_close, "current_close": current_close,
            "previous_reference": round(previous_reference, 8),
            "current_reference": round(current_reference, 8),
            "signal_key": sha256(identity.encode()).hexdigest()}
