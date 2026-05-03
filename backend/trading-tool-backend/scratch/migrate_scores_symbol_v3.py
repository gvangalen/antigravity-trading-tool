import asyncio
import sys
import os

# Pad toevoegen voor backend imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from sqlalchemy import text
from backend.infrastructure.database import engine

async def migrate():
    print("🚀 Final cleanup of constraints on 'daily_scores'...")
    async with engine.begin() as conn:
        # Drop old constraint
        try:
            await conn.execute(text("ALTER TABLE daily_scores DROP CONSTRAINT IF EXISTS daily_scores_user_report_date_unique;"))
            print("✅ Constraint 'daily_scores_user_report_date_unique' dropped.")
        except Exception as e:
            print(f"⚠️ Error: {e}")

        # Drop old unique index
        try:
            await conn.execute(text("DROP INDEX IF EXISTS daily_scores_user_date_idx;"))
            print("✅ Index 'daily_scores_user_date_idx' dropped.")
        except Exception as e:
            print(f"⚠️ Error: {e}")

        # Ensure new constraint exists
        try:
            await conn.execute(text("ALTER TABLE daily_scores ADD CONSTRAINT unique_user_symbol_date UNIQUE (user_id, symbol, report_date);"))
            print("✅ Multi-asset unique constraint added.")
        except Exception as e:
            if "already exists" in str(e):
                print("⚠️ Multi-asset unique constraint already exists.")
            else:
                print(f"❌ Error adding constraint: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
