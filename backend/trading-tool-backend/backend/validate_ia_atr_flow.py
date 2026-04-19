import sys
import os
import json
import logging

# Ensure project root is in path
sys.path.append(os.path.join(os.getcwd(), "backend", "trading-tool-backend"))

from backend.engine.backtest_engine import run_bot_backtest

# Configure logging
logging.basicConfig(level=logging.INFO)

# Load .env explicitly for standalone script
from dotenv import load_dotenv
env_path = os.path.join(os.getcwd(), "backend", "trading-tool-backend", "backend", ".env")
load_dotenv(env_path)

def test_ia_atr_flow():
    user_id = 30 # Henk
    bot_id = 16 # DCA Bot Long (Set as 'trade' type in DB)
    print(f"--- Running Backtest for Bot ID {bot_id} (Internal ID for Henk) ---")
    
    result = run_bot_backtest(user_id=user_id, bot_id=bot_id, scenario="default")
    
    if not result.get("ok"):
        print(f"Error: {result.get('error')}")
        return

    print(f"Bot: {result.get('bot_name')}")
    print(f"Return %: {result.get('return_pct')}%")
    print(f"Total Trades: {result.get('total_trades')}")
    
    perf = result.get("performance", {})
    print(f"Winrate: {perf.get('winrate')}% ({perf.get('wins')}W / {perf.get('losses')}L)")
    print(f"Expectancy: {perf.get('expectancy')}%")
    print(f"Summary: {result.get('summary', {}).get('message')}")
    
    print("\n--- Trade History (Last 5) ---")
    for t in result.get("trades", []):
        pnl = f" (PnL: {t['pnl_pct']}%)" if t.get('pnl_pct') is not None else ""
        reason = f" [{t.get('reason')}]" if t.get('reason') else ""
        print(f"[{t['date']}] {t['type'].upper()} at €{t['price']}{pnl}{reason} - Status: {t['status']}")

if __name__ == "__main__":
    test_ia_atr_flow()
