import asyncio
from sqlalchemy import select
from backend.infrastructure.models import User
from backend.infrastructure.database import async_session_factory
from backend.utils.auth_utils import hash_password

async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == 30))
        user = result.scalars().first()
        if user:
            print("FOUND USER 30:")
            print(f"ID: {user.id}")
            print(f"Email: {user.email}")
            user.password_hash = hash_password("password123")
            await session.commit()
            print("Successfully updated password to 'password123'!")
        else:
            print("USER 30 NOT FOUND")

if __name__ == "__main__":
    asyncio.run(main())
