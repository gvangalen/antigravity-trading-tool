import json
from datetime import date, timedelta
from backend.utils.db import get_db_connection
from backend.engine.backtest_engine import run_bot_backtest

def validate_exit():
    user_id = 30
    bot_id = 16
    strategy_id = 63
    setup_id = 61
    symbol = "BTC_TEST" # 🛡️ Use a dedicated test symbol to avoid corrupting live chart data
    
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Seed Day 2: Buy
        d2 = date.today() - timedelta(days=2)
        cur.execute("UPDATE market_data_7d SET open=67000, high=69000, low=66000, close=68000 WHERE symbol=%s AND date=%s", (symbol, d2))
        
        # Seed Day 1: TP hit (72k)
        d1 = date.today() - timedelta(days=1)
        # We need high to be >= 70000 (TP1)
        cur.execute("UPDATE market_data_7d SET open=68000, high=72000, low=67000, close=71000 WHERE symbol=%s AND date=%s", (symbol, d1))
        
        conn.commit()
    
    print(f"Testing TP Exit on {symbol}...")
    # Note: Bot config must also be set to use BTC_TEST for this test to be valid
    res = run_bot_backtest(user_id=user_id, bot_id=bot_id, days=2)
    conn.close()
    
    print(f"Total Trades: {res['total_trades']}")
    for t in res['trades']:
        print(f"Trade: {t['side']} at {t['price']} - Reason: {t.get('reason')}")
    
    # Expect 1 BUY and 1 SELL (Take Profit)
    # total_trades = 2 because it's incremented on both entry and exit in V1? 
    # Wait, let me check backtest_engine.py increment.
    # Line 253: state["total_trades"] += 1 (on BUY)
    # Line 172: state["total_trades"] += 1 (on SELL)
    
    if res['total_trades'] == 2 and any(t['reason'] == 'take_profit' for t in res['trades']):
        print("✅ PASS: Take Profit successfully triggered and closed position.")
    else:
        print("❌ FAIL: Take Profit not triggered as expected.")

if __name__ == "__main__":
    validate_exit()
