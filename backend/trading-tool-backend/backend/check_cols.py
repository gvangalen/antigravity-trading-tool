import asyncio
import os
import sys
from sqlalchemy import text

# Add parent dir to sys.path
sys.path.append(os.path.join(os.getcwd(), '..'))

from backend.infrastructure.database import engine

async def main():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='ai_category_insights'"))
        columns = [r[0] for r in res.fetchall()]
        print(f"Columns in ai_category_insights: {columns}")

if __name__ == "__main__":
    asyncio.run(main())
