import asyncio
import sys
import os

# Pad toevoegen zodat we backend imports kunnen doen
sys.path.append(os.path.join(os.getcwd(), "backend"))

from sqlalchemy import select
from backend.infrastructure.database import AsyncSessionLocal
from backend.infrastructure.models import MacroData, TechnicalDataIndicator
from backend.services.macro_data_service import MacroDataService
from backend.services.technical_data_service import TechnicalDataService

async def test_flow():
    print("🚀 Start Multi-Asset / Multi-User Flow Test...")
    
    async with AsyncSessionLocal() as session:
        macro_service = MacroDataService(session)
        tech_service = TechnicalDataService(session)
        
        user_a_id = 999  # Dummy ID
        user_b_id = 888  # Dummy ID
        
        # CLEANUP (voor het geval dat)
        await session.execute(text("DELETE FROM macro_data WHERE user_id IN (888, 999)"))
        await session.execute(text("DELETE FROM technical_indicators WHERE user_id IN (888, 999)"))
        await session.commit()

        # ---------------------------------------------------------
        # TEST 1: MACRO GLOBAL POOL
        # ---------------------------------------------------------
        print("\n--- TEST 1: Macro Global Pool ---")
        # User A voegt DXY toe (geen symbol opgegeven -> Global)
        await macro_service.add_macro_indicator(user_a_id, "DXY", 105.0)
        await session.commit()
        
        # Check BTC view voor User A
        indicators_btc = await macro_service.get_macro_indicators(user_a_id, symbol="BTC")
        print(f"User A (BTC) Macro Indicators: {[i.indicator for i in indicators_btc]}")
        
        # Check SOL view voor User A
        indicators_sol = await macro_service.get_macro_indicators(user_a_id, symbol="SOL")
        print(f"User A (SOL) Macro Indicators: {[i.indicator for i in indicators_sol]}")
        
        # Verificatie
        assert len(indicators_btc) == 1, "DXY moet bij BTC staan"
        assert len(indicators_sol) == 1, "DXY moet OOK bij SOL staan (Global Pool)"
        print("✅ Macro Global Pool werkt (User Visie overal gelijk)")

        # ---------------------------------------------------------
        # TEST 2: TECHNICAL ASSET FILTERING
        # ---------------------------------------------------------
        print("\n--- TEST 2: Technical Asset Filtering ---")
        # User A voegt RSI toe aan BTC
        await tech_service.add_technical_indicator("RSI", user_a_id, symbol="BTC")
        await session.commit()
        
        # Check BTC view
        tech_btc = await tech_service.get_indicators(user_a_id, symbol="BTC")
        print(f"User A (BTC) Technical Indicators: {[i.indicator for i in tech_btc]}")
        
        # Check SOL view
        tech_sol = await tech_service.get_indicators(user_a_id, symbol="SOL")
        print(f"User A (SOL) Technical Indicators: {[i.indicator for i in tech_sol]}")
        
        # Verificatie
        assert "rsi" in [i.indicator for i in tech_btc], "RSI moet bij BTC staan"
        assert len(tech_sol) == 0, "SOL moet leeg zijn (Technical is Asset-specifiek)"
        print("✅ Technical Asset Filtering werkt (Strakke scheiding)")

        # ---------------------------------------------------------
        # TEST 3: MULTI-USER ISOLATION
        # ---------------------------------------------------------
        print("\n--- TEST 3: Multi-User Isolation ---")
        # User B voegt S&P 500 toe
        await macro_service.add_macro_indicator(user_b_id, "S&P 500", 5000.0)
        await session.commit()
        
        # Check User A weer
        macro_a = await macro_service.get_macro_indicators(user_a_id)
        macro_b = await macro_service.get_macro_indicators(user_b_id)
        
        print(f"User A Indicators: {[i.indicator for i in macro_a]}")
        print(f"User B Indicators: {[i.indicator for i in macro_b]}")
        
        # Verificatie
        assert "DXY" in [i.name for i in macro_a]
        assert "S&P 500" in [i.name for i in macro_b]
        assert "S&P 500" not in [i.name for i in macro_a], "Data mag niet lekken tussen users"
        print("✅ Multi-User Isolation werkt")

from sqlalchemy import text
if __name__ == "__main__":
    asyncio.run(test_flow())
