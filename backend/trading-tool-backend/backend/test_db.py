import asyncio
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from backend.infrastructure.models import User
import os
from dotenv import load_dotenv

load_dotenv()
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "market_dashboard")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with async_session() as session:
        result = await session.execute(select(User))
        user = result.scalars().first()
        if user:
            print("FOUND USER:")
            print(f"ID: {user.id}")
            from datetime import datetime, timezone
            user.last_login_at = datetime.now(timezone.utc)
            await session.commit()
            print("Successfully updated user last_login_at!")
        else:
            print("NO USERS FOUND")

asyncio.run(main())
