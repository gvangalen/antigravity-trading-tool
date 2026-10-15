"""One owner-scoped portfolio projection for FINN, web, and mobile.

Budget limits never stand in for cash. Live broker holdings count once at the
account level; only explicitly allocated free EUR cash is attributed to bots.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from backend.schemas.finn_v2_evidence_schema import PortfolioBotData, PortfolioData, PortfolioGlobalData


def project_portfolio(
    payload: dict, *, asset: str | None = None, environment: str | None = None
) -> PortfolioData:
    if environment not in (None, "paper", "live"):
        raise ValueError("Unknown portfolio environment")
    symbol = str(asset or "").strip().upper() or None
    rows = [
        row for row in payload.get("bots", [])
        if (symbol is None or str(row.get("symbol") or "").strip().upper() == symbol)
        and (environment is None or bool(row.get("is_live")) == (environment == "live"))
    ]
    read_at = payload.get("read_at") or datetime.now(timezone.utc)
    mixed = len({bool(row.get("is_live")) for row in rows}) > 1
    live = bool(rows) and all(bool(row.get("is_live")) for row in rows)
    account = payload.get("live_account") if environment == "live" else None
    allocation_rows = payload.get("live_allocations") or {}
    live_allocations = {int(key): float(value) for key, value in allocation_rows.items()}
    account_positions = (account or {}).get("positions") or {}
    account_prices = (account or {}).get("prices_eur") or {}
    broker_qty_by_symbol: dict[str, float] = {}
    for row in rows:
        if row.get("is_live"):
            key = str(row.get("symbol") or "").strip().upper()
            broker_qty_by_symbol[key] = broker_qty_by_symbol.get(key, 0) + float(row.get("qty") or 0)
    quantity_reconciled = bool(account) and all(
        isfinite(qty) and qty >= -1e-9 and qty <= float(account_positions.get(key) or 0) + 1e-9
        for key, qty in broker_qty_by_symbol.items()
    )
    allocations_reconciled = bool(account) and all(
        isfinite(amount) and amount >= 0 for amount in live_allocations.values()
    ) and sum(live_allocations.values()) <= float(account["cash_eur"]) + 0.005
    unverified = any(row.get("unverified_ledger", False) for row in rows)
    initialized = bool(rows) and all(row.get("portfolio_initialized", True) and not row.get("unverified_ledger", False) for row in rows)
    priced = initialized and all(row.get("price_available", True) for row in rows)
    budget = sum(float(row.get("budget_total") or 0) for row in rows)

    # Paper cash is a funded virtual ledger balance. Live bot cash is not a
    # broker account balance and may be shared across several bots.
    cash = (
        sum(float(row.get("cash") or 0) for row in rows)
        if initialized and not mixed and not live else None
    )
    invested = sum(float(row.get("invested") or 0) for row in rows) if initialized else None
    realized = sum(float(row.get("realized_pnl") or 0) for row in rows) if initialized else None
    position_value = (
        sum(float(row.get("position_value") or 0) for row in rows)
        if priced else None
    )
    equity = cash + position_value if cash is not None and position_value is not None else None
    unrealized = position_value - invested if position_value is not None and invested is not None else None
    if environment == "live" and not account:
        invested = realized = position_value = unrealized = None

    allocations: dict[str, float] = {}
    if equity is not None and equity > 0:
        allocations["Cash"] = round(100 * cash / equity, 2)
        for row in rows:
            key = str(row.get("symbol") or "").strip().upper()
            if key:
                allocations[key] = allocations.get(key, 0) + 100 * float(row.get("position_value") or 0) / equity
        allocations = {key: round(value, 2) for key, value in allocations.items()}

    bots = []
    for row in rows:
        row_initialized = bool(row.get("portfolio_initialized", True)) and not bool(row.get("unverified_ledger", False))
        row_priced = row_initialized and bool(row.get("price_available", True))
        row_live = bool(row.get("is_live"))
        bot_id = int(row.get("bot_id") or 0)
        row_cash = (
            live_allocations.get(bot_id) if account and allocations_reconciled else None
        ) if row_live else (float(row.get("cash") or 0) if row_initialized else None)
        row_symbol = str(row.get("symbol") or "").strip().upper()
        row_qty = float(row.get("qty") or 0)
        if row_live:
            row_priced = not bool(row.get("unverified_ledger")) and bool(account) and quantity_reconciled and row_qty >= 0 and (
                row_qty == 0 or (row_initialized and row_symbol in account_prices)
            )
            row_position = row_qty * float(account_prices.get(row_symbol) or 0) if row_priced else None
        else:
            row_position = float(row.get("position_value") or 0) if row_priced else None
        row_invested = float(row.get("invested") or 0) if row_initialized and (not row_live or row_priced) else None
        row_realized = float(row.get("realized_pnl") or 0) if row_initialized and (not row_live or row_priced) else None
        row_unrealized = row_position - row_invested if row_position is not None and row_invested is not None else None
        bots.append(PortfolioBotData(
            bot_id=row.get("bot_id"), name=row.get("name"), symbol=row.get("symbol"),
            strategy_id=row.get("strategy_id"), strategy_name=row.get("strategy_name"),
            setup_id=row.get("setup_id"), setup_name=row.get("setup_name"), mode=row.get("mode"),
            equity=(row_cash + row_position if row_cash is not None and row_position is not None else None),
            cash_eur=row_cash, position_value_eur=row_position,
            position_qty=(float(row.get("qty") or 0) if row_initialized else None),
            invested_eur=row_invested, realized_pnl_eur=row_realized,
            unrealized_pnl_eur=row_unrealized,
            result_eur=(row_realized + row_unrealized if row_realized is not None and row_unrealized is not None else None),
            portfolio_initialized=row_initialized, valuation_available=(row_priced and row_cash is not None),
            valuation_status=(
                "unverified_ledger" if row.get("unverified_ledger") else
                "unreconciled_live" if row_live and not row_priced else
                "unallocated_live_cash" if row_live and row_cash is None else
                "unfunded" if not row_initialized else
                "missing_price" if not row_priced else "available"
            ),
            budget_total_eur=float(row.get("budget_total") or 0),
            paper_cash_eur=None if row_live else row_cash, is_active=row.get("is_active"), is_live=row_live,
            price_as_of=account.get("as_of") if row_live and account and row_qty else row.get("price_as_of"),
            price_quote_currency="EUR" if row_live and row_priced else row.get("price_quote_currency"),
            source_price_as_of=account.get("as_of") if row_live and account and row_qty else row.get("source_price_as_of"),
            fx_as_of=None if row_live else row.get("fx_as_of"),
            fx_eur_per_unit=None if row_live else row.get("fx_eur_per_unit"),
        ))

    if account and symbol is None:
        cash = float(account["total_eur"])
        position_value = (float(account["position_value_eur"])
                          if account["position_value_eur"] is not None else None)
        equity = cash + position_value if position_value is not None else None
        # Broker holdings may include manual positions. Ledger P&L is not an
        # account-wide result and must not be displayed as one.
        invested = realized = unrealized = None
        allocations = {}
        if equity is not None and equity > 0:
            allocations["Cash"] = round(100 * cash / equity, 2)
            for key, qty in account_positions.items():
                allocations[key] = round(100 * qty * account_prices[key] / equity, 2)

    held = [row for row in rows if float(row.get("qty") or 0) != 0]
    price_times = [row.get("price_as_of") for row in held]
    if account and symbol is None and equity is not None:
        valuation_as_of = account["as_of"]
    elif equity is not None and held and all(price_times):
        valuation_as_of = min(
            value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            for value in price_times
        )
    elif equity is not None and not held:
        valuation_as_of = read_at
    else:
        valuation_as_of = None

    if account and symbol is None:
        status = "available" if equity is not None else "missing_price"
    elif not rows:
        status = "empty"
    elif live:
        status = "unreconciled_live"
    elif unverified:
        status = "unverified_ledger"
    elif not initialized:
        status = "unfunded"
    elif not priced:
        status = "missing_price"
    elif mixed:
        status = "mixed_environments"
    else:
        status = "available"

    global_data = PortfolioGlobalData(
        currency="EUR", total_equity=equity, cash_balance=cash,
        invested_value=invested, current_position_value=position_value,
        realized_pnl=realized, unrealized_pnl=unrealized,
        total_budget_limit=budget, allocations_pct=allocations,
    )
    return PortfolioData.parse_obj({
        "global": global_data.dict(), "bots": [bot.dict() for bot in bots],
        "read_at": read_at, "valuation_as_of": valuation_as_of,
        "valuation_available": equity is not None,
        "valuation_status": status, "environment": environment,
        "unallocated_cash_eur": (
            round(max(0, float(account["cash_eur"]) - sum(live_allocations.values())), 2)
            if account and allocations_reconciled and symbol is None else None
        ),
        "available_cash_eur": float(account["cash_eur"]) if account and symbol is None else None,
        "reserved_cash_eur": round(float(account["total_eur"]) - float(account["cash_eur"]), 2) if account and symbol is None else None,
        "exchange_name": account.get("exchange_name") if account and symbol is None else None,
        "balance_time_basis": account.get("balance_time_basis") if account and symbol is None else None,
        "covered_scopes": [
            "paper_bot_portfolio_valuation" if rows and not live and not mixed else "bot_ledger",
            "broker_account_total" if account and symbol is None else "budget", "exposure",
        ],
        "excluded_scopes": (["trade_transaction_history", "tax_records", "tax_calculations"]
                            if account and symbol is None else
                            ["broker_account_total", "trade_transaction_history", "tax_records", "tax_calculations"]),
    })
