import json
from datetime import date, timedelta
from backend.utils.db import get_db_connection

def seed():
    conn = get_db_connection()
    user_id = 30
    strategy_id = 63
    setup_id = 61
    symbol = "BTC"
    
    with conn.cursor() as cur:
        # 0. Seed Regime Memory (force risk_on for boost)
        cur.execute("""
            INSERT INTO regime_memory (user_id, date, regime_label, confidence, signals_json, narrative)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
            ON CONFLICT (user_id, date) DO UPDATE SET regime_label = EXCLUDED.regime_label
        """, (user_id, "risk_on", 0.9, json.dumps({}), "Forced risk_on for validation"))

        # 1. Clear existing data for the test range to avoid conflicts
        cur.execute("DELETE FROM daily_scores WHERE user_id = %s AND report_date >= CURRENT_DATE - INTERVAL '31 days'", (user_id,))
        cur.execute("DELETE FROM active_strategy_snapshot WHERE user_id = %s AND strategy_id = %s AND snapshot_date >= CURRENT_DATE - INTERVAL '31 days'", (user_id, strategy_id))
        
        # 2. Seed 30 days of data
        for i in range(31):
            report_date = date.today() - timedelta(days=i)
            
            # Seed Market Data (OHLC)
            # Around 68k
            cur.execute("""
                INSERT INTO market_data_7d (symbol, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE 
                SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close
            """, (symbol, report_date, 67000.0, 69000.0, 66000.0, 68000.0, 1000.0))

            # Seed Daily Scores
            cur.execute("""
                INSERT INTO daily_scores (user_id, report_date, macro_score, technical_score, market_score, setup_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, report_date) DO UPDATE
                SET macro_score=EXCLUDED.macro_score, technical_score=EXCLUDED.technical_score, 
                    market_score=EXCLUDED.market_score, setup_score=EXCLUDED.setup_score
            """, (user_id, report_date, 95, 95, 95, 95))

            
            # Seed Strategy Snapshot
            # Entry 65k, TP 70k+75k, SL 60k
            targets = json.dumps([70000.0, 75000.0])
            cur.execute("""
                INSERT INTO active_strategy_snapshot (user_id, strategy_id, setup_id, snapshot_date, entry, targets, stop_loss, confidence_score, adjustment_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, setup_id, snapshot_date) DO UPDATE
                SET entry=EXCLUDED.entry, targets=EXCLUDED.targets, stop_loss=EXCLUDED.stop_loss,
                    confidence_score=EXCLUDED.confidence_score, adjustment_reason=EXCLUDED.adjustment_reason
            """, (user_id, strategy_id, setup_id, report_date, 65000.0, targets, 60000.0, 80, "Initial validation seed"))



            
        conn.commit()
    conn.close()
    print("✅ Seeded 30 days of backtest data for user 30, strategy 63.")

if __name__ == "__main__":
    seed()
