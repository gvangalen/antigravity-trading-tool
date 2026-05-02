import asyncio
from sqlalchemy import text
from backend.infrastructure.database import async_session_factory

async def add_base_currency_column():
    async with async_session_factory() as session:
        try:
            print("🚀 Adding 'base_currency' column to 'bot_configs'...")
            # 1. Add column
            await session.execute(text("ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS base_currency VARCHAR(10) DEFAULT 'EUR'"))
            # 2. Update existing rows to 'EUR' if they are null
            await session.execute(text("UPDATE bot_configs SET base_currency = 'EUR' WHERE base_currency IS NULL"))
            await session.commit()
            print("✅ Column added successfully!")
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(add_base_currency_column())
