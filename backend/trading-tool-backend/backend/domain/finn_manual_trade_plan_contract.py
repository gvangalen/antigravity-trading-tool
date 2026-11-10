"""Validated, non-executable manual trade plans for FINN proposals.

The calculated amounts are in the instrument's quote currency.  They are
planning estimates, not exchange orders or portfolio-risk percentages.
"""

from __future__ import annotations

from decimal import Decimal, DecimalException, InvalidOperation
import re
from typing import Any

from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG


def _positive_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field}_invalid")
    raw = format(value, ".12f") if isinstance(value, float) else str(value)
    # Bound untrusted input before Decimal parses it or arithmetic allocates
    # large coefficients. Prices and quantities may use at most 12 decimals.
    if len(raw) > 32 or not re.fullmatch(r"(?:0|[1-9]\d{0,11})(?:\.\d{1,12})?", raw):
        raise ValueError(f"{field}_invalid")
    try:
        number = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field}_invalid") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{field}_invalid")
    return number


def validate_manual_trade_plan(fields: dict[str, Any]) -> dict[str, Any]:
    """Validate user-selected terms and calculate risk without market guesses."""
    allowed = {
        "asset", "quote_currency", "direction", "entry_type", "entry_price",
        "quantity", "stop_loss", "targets",
    }
    derived = {
        "asset_class", "venue", "position_value_quote", "risk_per_unit_quote",
        "max_loss_quote", "risk_pct_of_position", "reward_risk_by_target",
        "executable", "level_source", "risk_assumption",
    }
    if set(fields).difference(allowed | derived):
        raise ValueError("manual_trade_unknown_field")
    asset = str(fields.get("asset") or "").strip().upper()
    catalog = DEFAULT_ASSET_CATALOG.get(asset)
    if not catalog:
        raise ValueError("manual_trade_asset_not_in_catalog")
    quote = str(fields.get("quote_currency") or "").strip().upper()
    if not quote:
        raise ValueError("manual_trade_quote_required")
    asset_class = str(catalog.get("asset_class") or "").lower()
    if asset_class == "stock":
        if quote != str(catalog.get("quote_currency") or "").upper():
            raise ValueError("manual_trade_quote_not_in_catalog")
    elif asset_class == "crypto":
        if quote not in {"EUR", "USDT"}:
            raise ValueError("manual_trade_quote_not_in_catalog")
    else:
        raise ValueError("manual_trade_asset_class_unsupported")
    direction = str(fields.get("direction") or "").strip().lower()
    if direction not in {"long", "short"}:
        raise ValueError("manual_trade_direction_required")
    entry_type = str(fields.get("entry_type") or "").strip().lower()
    if entry_type != "limit":
        raise ValueError("manual_trade_entry_type_unsupported")
    entry = _positive_decimal(fields.get("entry_price"), "entry_price")
    quantity = _positive_decimal(fields.get("quantity"), "quantity")
    stop = _positive_decimal(fields.get("stop_loss"), "stop_loss")
    raw_targets = fields.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets or len(raw_targets) > 5:
        raise ValueError("manual_trade_targets_required")
    targets = [_positive_decimal(item, "target") for item in raw_targets]
    if len(set(targets)) != len(targets):
        raise ValueError("manual_trade_duplicate_target")
    if direction == "long":
        if not stop < entry or any(target <= entry for target in targets):
            raise ValueError("manual_trade_price_geometry_invalid")
        targets.sort()
        risk_per_unit = entry - stop
        rewards = [target - entry for target in targets]
    else:
        if not stop > entry or any(target >= entry for target in targets):
            raise ValueError("manual_trade_price_geometry_invalid")
        targets.sort(reverse=True)
        risk_per_unit = stop - entry
        rewards = [entry - target for target in targets]
    try:
        notional = entry * quantity
        maximum_loss = risk_per_unit * quantity
        risk_pct = (risk_per_unit / entry) * Decimal("100")
        ratios = [reward / risk_per_unit for reward in rewards]
    except DecimalException as exc:
        raise ValueError("manual_trade_calculation_invalid") from exc
    if not all(value.is_finite() for value in [notional, maximum_loss, risk_pct, *ratios]):
        raise ValueError("manual_trade_calculation_invalid")
    result = {
        "asset": asset,
        "quote_currency": quote,
        "asset_class": asset_class,
        "venue": str(catalog.get("exchange") or "").upper(),
        "direction": direction,
        "entry_type": entry_type,
        "entry_price": str(entry),
        "quantity": str(quantity),
        "stop_loss": str(stop),
        "targets": [str(target) for target in targets],
        "position_value_quote": str(notional),
        "risk_per_unit_quote": str(risk_per_unit),
        "max_loss_quote": str(maximum_loss),
        "risk_pct_of_position": str(risk_pct),
        "reward_risk_by_target": [str(value) for value in ratios],
        "level_source": "user_stated",
        "risk_assumption": "price_only_excludes_fees_slippage_and_gaps",
        "executable": False,
    }
    # Re-parsing a sealed proposal is safe, but a caller cannot choose its
    # computed risk, venue, or execution status independently of the terms.
    if any(fields[key] != result[key] for key in derived if key in fields):
        raise ValueError("manual_trade_computed_field_mismatch")
    return result
