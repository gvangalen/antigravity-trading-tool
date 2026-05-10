import asyncio
from sqlalchemy import select
from backend.infrastructure.models import User
from backend.infrastructure.database import async_session_factory

async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == 30))
        user = result.scalars().first()
        if user:
            print("FOUND USER 30:")
            print(f"ID: {user.id}")
            print(f"Email: {user.email}")
            print(f"Role: {user.role}")
            print(f"First Name: {user.first_name}")
            print(f"Last Name: {user.last_name}")
            print(f"Is Active: {user.is_active}")
        else:
            print("USER 30 NOT FOUND")

if __name__ == "__main__":
    asyncio.run(main())
