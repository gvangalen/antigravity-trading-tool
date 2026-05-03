import asyncio
import sys
import os

# Pad toevoegen voor backend imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from sqlalchemy import text
from backend.infrastructure.database import engine

async def migrate():
    print("🚀 Adding 'symbol' column to 'technical_indicators' table...")
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE technical_indicators ADD COLUMN symbol VARCHAR(20) DEFAULT 'BTC';"))
            print("✅ Column 'symbol' added successfully.")
        except Exception as e:
            if "already exists" in str(e):
                print("⚠️ Column 'symbol' already exists.")
            else:
                print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
