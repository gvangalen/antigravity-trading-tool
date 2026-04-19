import json
from datetime import date
from backend.utils.db import get_db_connection
from backend.engine.backtest_engine import run_bot_backtest
from backend.engine.bot_brain import run_bot_brain
from backend.ai_agents.trading_bot_agent import _get_daily_scores, _get_active_strategy_snapshot, _get_strategy_setup_payload

def validate_parity():
    user_id = 30
    bot_id = 16
    strategy_id = 63
    report_date = date.today()
    
    conn = get_db_connection()
    
    # 1. Fetch data as bot_brain would
    setup = _get_strategy_setup_payload(conn, user_id=user_id, strategy_id=strategy_id)
    scores = _get_daily_scores(conn, user_id=user_id, report_date=report_date)
    snapshot = _get_active_strategy_snapshot(conn, user_id=user_id, strategy_id=strategy_id, report_date=report_date)
    if snapshot:
        snapshot["confidence_score"] = snapshot.get("confidence") # Sync keys
    
    # Mock portfolio context for a live call
    portfolio_context = {
        "live_price": 68000.0, # BTC price
        "cash_eur": 1000.0,
        "asset_qty": 0.0,
        "portfolio_value_eur": 1000.0,
        "active_strategy": snapshot,
        "symbol": "BTC",
        "today_allocated_eur": 0.0,
        "kill_switch": True
    }
    
    # Brain Decision
    brain_res = run_bot_brain(
        user_id=user_id,
        setup=setup,
        scores=scores,
        portfolio_context=portfolio_context
    )
    
    # 2. Run Backtest for exactly 1 day (today)
    bt_res = run_bot_backtest(user_id=user_id, bot_id=bot_id, days=1)
    
    conn.close()
    
    if not bt_res.get("ok"):
        print(f"❌ BACKTEST API ERROR: {bt_res.get('error')}")
        return

    print("\n--- BRAIN DECISION ---")
    print(f"Action: {brain_res['action']}")
    print(f"Confidence: {brain_res['confidence']}")
    print(f"Reason: {brain_res['reason']}")
    print(f"Debug Snapshot Keys: {brain_res.get('debug', {}).get('snapshot', {}).keys()}")
    
    print("\n--- BACKTEST RESULT ---")
    print(f"Total Trades: {bt_res['total_trades']}")
    print(f"Final Balance: {bt_res['final_balance']}")

    
    # Check if backtest actually executed the trade the brain suggested
    if brain_res['action'] == "buy" and bt_res['total_trades'] > 0:
        print("✅ PASS: Parity matches. Brain said BUY and Backtest executed trade.")
    elif brain_res['action'] == "hold" and bt_res['total_trades'] == 0:
        print("✅ PASS: Parity matches. Brain said HOLD and Backtest stayed flat.")
    else:
        print("❌ FAIL: Parity mismatch!")
        if brain_res['action'] == "buy":
             print("Reason: Brain said BUY but Backtest did not trade.")
        else:
             print("Reason: Brain said HOLD but Backtest traded.")

if __name__ == "__main__":
    validate_parity()
