import logging
import json
from datetime import date, timedelta, datetime
from typing import Any, Dict, List, Optional

from backend.utils.db import get_db_connection
from backend.engine.bot_brain import run_bot_brain

# Reuse helpers from trading_bot_agent where possible
# Note: In a real refactor we'd move these to a shared service, 
# but for V1 we keep it focused.
from backend.ai_agents.trading_bot_agent import (
    _get_strategy_setup_payload,
    _get_active_strategy_snapshot,
    _get_daily_scores,
    _build_setup_match,
    _ledger_deltas,
    _normalize_action,
    _map_confidence
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_SYMBOL = "BTC"

def get_historical_candles(conn, symbol: str, days: int) -> List[Dict[str, Any]]:
    """
    Fetches historical candles from market_data_7d.
    Even though the table name says 7d, it often contains more in some setups,
    or we use it as the source for daily OHLC.
    """
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    start_date = date.today() - timedelta(days=days)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM market_data_7d
            WHERE symbol = %s AND date >= %s
            ORDER BY date ASC
        """, (symbol, start_date))
        rows = cur.fetchall()
        
    return [
        {
            "date": r[0],
            "open": float(r[1] or 0),
            "high": float(r[2] or 0),
            "low": float(r[3] or 0),
            "close": float(r[4] or 0),
            "volume": float(r[5] or 0)
        }
        for r in rows
    ]

def run_bot_backtest(
    user_id: int,
    bot_id: int,
    days: int = 30,
    scenario: str = "default"
) -> Dict[str, Any]:
    """
    Runs a full backtest simulation for a specific bot with enriched output.
    """
    conn = get_db_connection()
    if not conn:
        return {"ok": False, "error": "db_unavailable"}

    # Scenario Multipliers
    multipliers = {
        "default": 1.0,
        "aggressive": 1.5,
        "conservative": 0.7
    }
    multiplier = multipliers.get(scenario, 1.0)

    try:
        # 1. Get Bot Config
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                  b.id, b.name, b.strategy_id, s.setup_id, st.symbol, st.timeframe,
                  COALESCE(b.budget_total_eur, 0),
                  COALESCE(b.budget_daily_limit_eur, 0),
                  COALESCE(b.budget_min_order_eur, 0),
                  COALESCE(b.budget_max_order_eur, 0),
                  COALESCE(b.max_asset_exposure_pct, 100),
                  s.setup_type
                FROM bot_configs b
                JOIN strategies s ON s.id = b.strategy_id
                JOIN setups st    ON st.id = s.setup_id
                WHERE b.id = %s AND b.user_id = %s
            """, (bot_id, user_id))
            row = cur.fetchone()
            
        if not row:
            return {"ok": False, "error": "bot_not_found"}

        bot_id, bot_name, strategy_id, setup_id, symbol, timeframe, \
        total_budget, daily_limit, min_order, max_order, max_exposure, setup_type_raw = row

        symbol = symbol.upper()
        
        # 2. Get Historical Candles
        candles = get_historical_candles(conn, symbol, days)
        if not candles:
            return {"ok": False, "error": "no_historical_data"}

        # 3. Initialize State
        state = {
            "cash_eur": float(total_budget) if total_budget > 0 else 1000.0,
            "asset_qty": 0.0,
            "total_trades": 0,
            "trades": [],
            "wins": 0,
            "losses": 0,
            "total_invested": 0.0 # To track avg entry price
        }
        
        initial_balance = state["cash_eur"]
        current_position = None # { 'qty': ..., 'stop_loss': ..., 'targets': [...] }
        avg_entry_price = 0.0

        # 4. Simulation Loop
        for candle in candles:
            report_date = candle["date"]
            price_close = candle["close"]
            price_high = candle["high"]
            price_low = candle["low"]

            # Check Exits first if we have a position
            if current_position:
                exit_triggered = False
                exit_price = None
                exit_reason = ""

                # Stop Loss check
                if current_position["stop_loss"] and price_low <= current_position["stop_loss"]:
                    exit_triggered = True
                    exit_price = current_position["stop_loss"]
                    exit_reason = "stop_loss"
                
                # Targets check
                if not exit_triggered and current_position["targets"]:
                    for tp in current_position["targets"]:
                        if price_high >= tp:
                            exit_triggered = True
                            exit_price = tp
                            exit_reason = "take_profit"
                            break
                
                if exit_triggered:
                    cash_delta, qty_delta, notional = _ledger_deltas("sell", current_position["qty"], exit_price)
                    
                    # PnL Calculation
                    pnl_pct = round(((exit_price - avg_entry_price) / avg_entry_price) * 100, 2)
                    if pnl_pct > 0: state["wins"] += 1
                    else: state["losses"] += 1

                    state["cash_eur"] += cash_delta
                    state["asset_qty"] += qty_delta
                    state["trades"].append({
                        "type": "sell",
                        "date": report_date.isoformat(),
                        "price": exit_price,
                        "qty": current_position["qty"],
                        "amount_eur": round(notional, 2),
                        "pnl_pct": pnl_pct,
                        "status": "closed",
                        "reason": exit_reason
                    })
                    current_position = None
                    avg_entry_price = 0.0
                    state["total_invested"] = 0.0
                    state["total_trades"] += 1

            # Get Context for Brain
            scores = _get_daily_scores(conn, user_id, report_date)
            snapshot = _get_active_strategy_snapshot(conn, user_id, strategy_id, report_date)
            
            if not snapshot or not scores or (scores.get('macro') == 10 and scores.get('technical') == 10):
                continue

            setup_payload = _get_strategy_setup_payload(
                conn, user_id=user_id, strategy_id=strategy_id, 
                setup_id=setup_id, setup_name=setup_type_raw, symbol=symbol
            )
            
            portfolio_value_eur = state["cash_eur"] + (state["asset_qty"] * price_close)
            portfolio_context = {
                "today_allocated_eur": 0,
                "portfolio_value_eur": portfolio_value_eur,
                "current_asset_value_eur": state["asset_qty"] * price_close,
                "max_trade_risk_eur": max_order,
                "daily_allocation_eur": daily_limit,
                "max_asset_exposure_pct": max_exposure,
                "total_budget_eur": None,
                "kill_switch": True,
                "live_price": price_close,
                "high": price_high,
                "low": price_low,
                "active_strategy": snapshot,
            }

            # Run Brain
            brain = run_bot_brain(
                user_id=user_id,
                setup=setup_payload,
                scores={
                    "macro_score": scores.get("macro"),
                    "technical_score": scores.get("technical"),
                    "market_score": scores.get("market"),
                    "setup_score": scores.get("setup"),
                },
                portfolio_context=portfolio_context,
                backtest_mode=True,
            )

            action = _normalize_action(brain.get("action"))
            
            # --- EXECUTION ---
            
            # 1. Close position if brain says SELL
            if action == "sell" and current_position:
                qty_to_sell = current_position["qty"]
                cash_delta, qty_delta, notional = _ledger_deltas("sell", qty_to_sell, price_close)
                
                pnl_pct = round(((price_close - avg_entry_price) / avg_entry_price) * 100, 2)
                if pnl_pct > 0: state["wins"] += 1
                else: state["losses"] += 1

                state["cash_eur"] += cash_delta
                state["asset_qty"] += qty_delta
                
                state["trades"].append({
                    "type": "sell",
                    "date": report_date.isoformat(),
                    "price": price_close,
                    "qty": qty_to_sell,
                    "amount_eur": round(notional, 2),
                    "pnl_pct": pnl_pct,
                    "status": "closed",
                    "reason": brain.get("reason") or "brain_signal"
                })
                current_position = None
                avg_entry_price = 0.0
                state["total_invested"] = 0.0
                state["total_trades"] += 1

            # 2. Execute Buy if brain says buy (Support DCA by allowing multiple buys)
            elif action == "buy":
                amount_eur = float(brain.get("amount_eur") or 0) * multiplier
                if amount_eur > state["cash_eur"]:
                    amount_eur = state["cash_eur"]
                
                if amount_eur > 0:
                    qty = amount_eur / price_close
                    cash_delta, qty_delta, notional = _ledger_deltas("buy", qty, price_close)
                    
                    state["cash_eur"] += cash_delta
                    state["asset_qty"] += qty_delta
                    
                    # Update Avg Entry Price
                    new_total_qty = state["asset_qty"]
                    state["total_invested"] += round(notional, 2)
                    avg_entry_price = state["total_invested"] / new_total_qty
                    
                    trade_plan = brain.get("trade_plan") or {}
                    sl_price = (trade_plan.get("stop_loss") or {}).get("price")
                    tp_list = [t.get("price") for t in (trade_plan.get("targets") or []) if t.get("price")]

                    # Update or Create position
                    if not current_position:
                        current_position = {
                            "qty": qty,
                            "stop_loss": sl_price,
                            "targets": tp_list
                        }
                    else:
                        current_position["qty"] = new_total_qty
                        # Update targets/SL if brain provides new ones
                        if sl_price: current_position["stop_loss"] = sl_price
                        if tp_list: current_position["targets"] = tp_list

                    state["trades"].append({
                        "type": "buy",
                        "date": report_date.isoformat(),
                        "price": price_close,
                        "qty": qty,
                        "amount_eur": round(notional, 2),
                        "pnl_pct": None,
                        "status": "open",
                        "reason": brain.get("reason")
                    })
                    state["total_trades"] += 1

        # 5. Finalize results
        final_asset_value = state["asset_qty"] * (candles[-1]["close"] if candles else 0)
        final_balance = state["cash_eur"] + final_asset_value
        return_pct = round(((final_balance - initial_balance) / initial_balance) * 100, 2)

        # 6. Performance Metrics
        closed_trades = [t for t in state["trades"] if t.get("status") == "closed"]
        pnl_pcts = [t["pnl_pct"] for t in closed_trades if t.get("pnl_pct") is not None]
        
        wins = [p for p in pnl_pcts if p > 0]
        losses = [p for p in pnl_pcts if p <= 0]
        
        winrate = round((len(wins) / len(pnl_pcts) * 100), 2) if pnl_pcts else 0
        avg_win = round(sum(wins) / len(wins), 2) if wins else 0
        avg_loss = round(sum(losses) / len(losses), 2) if losses else 0
        
        # Expectancy = (winrate/100 * avg_win) - ((1 - winrate/100) * abs(avg_loss))
        expectancy = round(((winrate / 100) * avg_win) - ((1 - winrate / 100) * abs(avg_loss)), 2)

        # Detect strategy type
        strategy_type = "dca" if any(len(t.get("parts", [])) > 0 for t in state["trades"]) else "trading"

        performance = {
            "initial_balance": round(initial_balance, 2),
            "final_balance": round(final_balance, 2),
            "profit_eur": round(final_balance - initial_balance, 2),
            "return_pct": return_pct,
            "winrate": winrate,
            "wins": len(wins),
            "losses": len(losses),
            "total_trades": state["total_trades"],
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "best_trade_pct": round(max(pnl_pcts), 2) if pnl_pcts else 0,
            "worst_trade_pct": round(min(pnl_pcts), 2) if pnl_pcts else 0,
            "expectancy": expectancy,
            "strategy_type": strategy_type
        }

        # 7. Summary Logic
        total_trades = state["total_trades"]
        
        if total_trades < 5:
            msg = "Te weinig data voor een betrouwbare analyse"
        elif winrate >= 70 and expectancy > 1.0:
            msg = "Sterke strategie met een zeer consistente winst"
        elif winrate >= 70 and expectancy > 0:
            msg = "Sterke winrate, maar winsten per trade zijn beperkt"
        elif winrate >= 70 and expectancy <= 0:
            msg = "Hoge winrate, maar verliezen maken de strategie negatief"
        elif winrate < 50:
            msg = "Strategie presteert momenteel zwak"
        elif return_pct > 0:
            msg = "Bot is licht winstgevend, maar er is ruimte voor optimalisatie"
        else:
            msg = "Bot is verlieslatend. Overweeg je guardrails of strategy aan te passen."

        summary = {
            "message": msg,
            "wins": len(wins),
            "losses": len(losses),
            "open_positions": len([t for t in state["trades"] if t["status"] == "open"])
        }

        return {
            "ok": True,
            "bot_id": bot_id,
            "bot_name": bot_name,
            "scenario": scenario,
            "initial_balance": round(initial_balance, 2),
            "final_balance": round(final_balance, 2),
            "return_pct": return_pct,
            "total_trades": state["total_trades"],
            "trades": state["trades"][-5:], # Last 5 for list
            "performance": performance,
            "summary": summary
        }

    except Exception as e:
        logger.exception("Backtest failed")
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()
