import sys
import os
import asyncio
from sqlalchemy import text

# Voeg project root toe aan path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "trading-tool-backend")))

from backend.infrastructure.database import engine, Base
# Importeer alle modellen zodat ze bekend zijn bij Base.metadata
import backend.infrastructure.models 

async def sync_db():
    print("🔄 Syncing database models...")
    async with engine.begin() as conn:
        # Dit maakt alle tabellen aan die nog niet bestaan
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database sync complete.")

if __name__ == "__main__":
    asyncio.run(sync_db())
