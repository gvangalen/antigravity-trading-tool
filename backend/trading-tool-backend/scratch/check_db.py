
import asyncio
from backend.utils.db import get_db_connection

def check_watchlist():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM daily_scores LIMIT 10")
    rows = cur.fetchall()
    print(f"Symbols found: {rows}")
    conn.close()

if __name__ == "__main__":
    check_watchlist()
