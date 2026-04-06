import asyncio
import os
import sys

# Backend root to sys.path
sys.path.append(os.getcwd())

from backend.infrastructure.database import async_session_factory
from backend.services.technical_data_service import TechnicalDataService
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository

async def test_add_indicator():
    async with async_session_factory() as session:
        service = TechnicalDataService(session)
        
        user_id = 30
        indicator_name = "rsi"
        
        print(f"--- Testing add_technical_indicator for '{indicator_name}' (User {user_id}) ---")
        try:
            result = await service.add_technical_indicator(indicator_name, user_id)
            print("✅ Success!")
            print(result)
        except ValueError as ve:
            print(f"❌ Failed with ValueError: {ve}")
        except Exception as e:
            print(f"🔥 Crashed with error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_add_indicator())
