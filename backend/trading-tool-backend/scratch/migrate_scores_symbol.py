import asyncio
import sys
import os

# Pad toevoegen voor backend imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from sqlalchemy import text
from backend.infrastructure.database import engine

async def migrate():
    print("🚀 Migrating 'daily_scores' table...")
    async with engine.begin() as conn:
        # Add symbol column
        try:
            await conn.execute(text("ALTER TABLE daily_scores ADD COLUMN symbol VARCHAR(20) DEFAULT 'BTC';"))
            print("✅ Column 'symbol' added.")
        except Exception as e:
            if "already exists" in str(e):
                print("⚠️ Column 'symbol' already exists.")
            else:
                print(f"❌ Error adding column: {e}")

        # Update uniqueness constraint: (user_id, symbol, report_date)
        try:
            # Eerst oude constraint verwijderen indien die bestaat (vaak een unnamed primary key of unique index)
            # We maken een nieuwe unique constraint
            await conn.execute(text("ALTER TABLE daily_scores ADD CONSTRAINT unique_user_symbol_date UNIQUE (user_id, symbol, report_date);"))
            print("✅ Unique constraint (user_id, symbol, report_date) added.")
        except Exception as e:
            if "already exists" in str(e):
                print("⚠️ Unique constraint already exists.")
            else:
                print(f"❌ Error adding constraint: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
