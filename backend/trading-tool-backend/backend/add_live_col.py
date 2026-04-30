import asyncio
import os
import sys
from sqlalchemy import text

# Add parent dir to sys.path
sys.path.append(os.path.join(os.getcwd(), '..'))

from backend.infrastructure.database import sync_engine

def main():
    with sync_engine.connect() as conn:
        conn.execute(text("ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS is_live BOOLEAN DEFAULT FALSE"))
        conn.commit()
        print("✅ is_live column added to bot_configs")

if __name__ == "__main__":
    main()
