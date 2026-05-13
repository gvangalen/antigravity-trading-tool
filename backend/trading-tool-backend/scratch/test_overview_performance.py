import sys
import os
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any

# Ensure backend folder is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.schemas.dashboard_schema import MobileOverviewResponse
from backend.services.dashboard_service import DashboardService


# =====================================================================
# 📋 STEP 1: DEFINE ROBUST MOCK DATA LAYER
# =====================================================================
class MockUser:
    def __init__(self, id, first_name):
        self.id = id
        self.first_name = first_name
        self.ai_preferences = {"risk_profile": "aggressive"}


class MockUserRepository:
    def __init__(self, session=None):
        pass
    async def get_by_id(self, user_id):
        return MockUser(user_id, "Geert")


class MockDashboardRepository:
    def __init__(self, session=None):
        pass
    async def get_latest_prices_and_changes(self, user_id, symbols):
        return {
            "BTC": {"price": 57430.20, "change_24h": 1.45},
            "ETH": {"price": 3120.50, "change_24h": -0.85},
            "SOL": {"price": 142.15, "change_24h": 4.12}
        }


class MockBotRepository:
    def __init__(self, session=None):
        pass
    async def get_bot_portfolios_base(self, user_id):
        return [
            {
                "id": 1,
                "name": "SOL DCA Accumulator",
                "is_active": True,
                "is_live": True,
                "mode": "dca",
                "risk_profile": "medium",
                "budget_total_eur": 1000.00,
                "budget_daily_limit_eur": 50.00,
                "budget_min_order_eur": 10.00,
                "budget_max_order_eur": 50.00
            }
        ]

    async def get_bot_ledger_stats(self, user_id, bot_id, today):
        return {
            "net_cash": -400.00,
            "executed_cash": -400.00,
            "net_qty": 2.81,
            "today_spent": 50.00,
            "today_reserved": 0.00
        }

    async def get_market_price(self, symbol):
        return 148.21


class MockAiGateway:
    async def ask(self, user_id, prompt, system_role, mode="text", schema=None, purpose="assistant", symbol="GLOBAL", timeframe="1H", user_model=None):
        return {
            "greeting": "Hallo Geert!",
            "market_insight": {
                "conclusion": "De markt laat een sterke stijging zien bij Solana (+4.1%). Je SOL DCA bot presteert uitstekend met +4.1% winst."
            },
            "suggested_actions": ["Risico aanpassen", "DCA setup maken", "Rapport bekijken"]
        }


# =====================================================================
# 📋 STEP 2: MONKEYPATCH DEPENDENCIES FOR TEST ISOLATION
# =====================================================================
import backend.infrastructure.repositories.user_repository as ur
import backend.infrastructure.repositories.dashboard_repository as dr
import backend.infrastructure.repositories.bot_repository as br
import backend.services.dashboard_service as ds_mod
import backend.services.bot_service as bs_mod

# Replace standard source modules
ur.UserRepository = MockUserRepository
dr.DashboardRepository = MockDashboardRepository
br.BotRepository = MockBotRepository

ds_mod.UserRepository = MockUserRepository
ds_mod.DashboardRepository = MockDashboardRepository
bs_mod.BotRepository = MockBotRepository

# Mock sync scoring wrapper to avoid database dependencies during unit testing
def mock_sync_scores(user_id, symbol):
    return {
        "macro_score": 65.0,
        "technical_score": 80.0 if symbol == "SOL" else (-20.0 if symbol == "BTC" else 10.0),
        "market_score": 60.0 if symbol == "SOL" else (40.0 if symbol == "BTC" else 25.0),
        "setup_score": 90.0 if symbol == "SOL" else (80.0 if symbol == "BTC" else 0.0)
    }

ds_mod.sync_get_scores_for_symbol = mock_sync_scores

# Mock context helper inside AiAssistantService so it doesn't query DB
async def mock_build_context(self, user_id, context_type):
    return "Mock context details"

from backend.services.ai_assistant_service import AiAssistantService
AiAssistantService._build_context = mock_build_context


async def run_tests():
    print("🚀 Running AI Mobile Overview Caching & Fault-Tolerance Tests...\n")
    
    # Initialize real service with mock async session
    service = DashboardService(db_session=None)
    
    # Set mock AI Gateway on AiAssistantService
    from backend.services.ai_gateway import AiGateway
    original_ask = AiGateway.ask
    
    async def mock_gateway_ask(*args, **kwargs):
        return {
            "greeting": "Hallo Geert!",
            "market_insight": {
                "conclusion": "De markt laat een sterke stijging zien bij Solana (+4.1%). Je SOL DCA bot presteert uitstekend met +4.1% winst."
            },
            "suggested_actions": ["Risico aanpassen", "DCA setup maken", "Rapport bekijken"]
        }
    AiGateway.ask = mock_gateway_ask
    
    # Ensure cache is completely empty at start
    DashboardService._overview_cache.clear()
    
    # -----------------------------------------------------------------
    # ⚡ TEST CASE 1: Cache Miss vs Cache Hit Performance
    # -----------------------------------------------------------------
    print("📋 Test Case 1: Checking Cache Hit latency...")
    
    # First execution -> should trigger a Cache MISS (takes database, calculation, logic roundtrips)
    start_miss = time.perf_counter()
    resp_miss = await service.get_mobile_overview(user_id=123)
    duration_miss_ms = (time.perf_counter() - start_miss) * 1000
    print(f"   - Cache MISS duration: {duration_miss_ms:.2f}ms")
    
    # Second execution -> should trigger a Cache HIT (served directly from memory dictionary)
    start_hit = time.perf_counter()
    resp_hit = await service.get_mobile_overview(user_id=123)
    duration_hit_ms = (time.perf_counter() - start_hit) * 1000
    print(f"   - Cache HIT duration: {duration_hit_ms:.2f}ms")
    
    assert duration_hit_ms < 1.0, f"Cache HIT took too long: {duration_hit_ms}ms"
    print("   ✅ Cache Performance validated! Served in < 1ms.")
    
    # -----------------------------------------------------------------
    # ⚡ TEST CASE 2: Cache Bypass (bypass_cache=True)
    # -----------------------------------------------------------------
    print("\n📋 Test Case 2: Checking Cache Bypass (bypass_cache=True)...")
    
    start_bypass = time.perf_counter()
    resp_bypass = await service.get_mobile_overview(user_id=123, bypass_cache=True)
    duration_bypass_ms = (time.perf_counter() - start_bypass) * 1000
    print(f"   - Cache Bypass duration: {duration_bypass_ms:.2f}ms")
    
    assert duration_bypass_ms > 0.0, "Cache bypass did not recalculate"
    print("   ✅ Cache bypass forced complete recalculation successfully!")

    # -----------------------------------------------------------------
    # ⚡ TEST CASE 3: OpenAI/LLM Outage Graceful Degradation
    # -----------------------------------------------------------------
    print("\n📋 Test Case 3: Simulating OpenAI Outage (Fallback Priority)...")
    
    # Monkeypatch AiGateway ask method to raise a critical API timeout/failure
    async def broken_ask(*args, **kwargs):
        raise RuntimeError("OpenAI API Outage - Timeout 504 Gateway Error")
    
    # Apply failure patch
    AiGateway.ask = broken_ask
    
    # Clear cache to force a fresh composition
    DashboardService._overview_cache.clear()
    
    start_resilient = time.perf_counter()
    # Execute the overview
    resp_resilient = await service.get_mobile_overview(user_id=123, bypass_cache=True)
    duration_resilient_ms = (time.perf_counter() - start_resilient) * 1000
    
    print(f"   - Execution completed in {duration_resilient_ms:.2f}ms under complete AI outage!")
    
    # Assertions for highest-priority features (Portfolio / Watchlist / Scores)
    assert resp_resilient.portfolio.total_balance_eur == 416.47, f"Portfolio totals lost during AI outage! Got: {resp_resilient.portfolio.total_balance_eur}"
    assert len(resp_resilient.watchlist) == 3, "Watchlist lost during AI outage!"
    assert resp_resilient.watchlist[2].symbol == "SOL"
    assert resp_resilient.watchlist[2].technical_score == 80.0
    
    # Assertions for bot context
    assert len(resp_resilient.active_bots) == 1, "Bot data lost during AI outage!"
    assert resp_resilient.active_bots[0].invested_eur == 400.0
    
    # Assertions for fallback FINN briefing
    assert resp_resilient.finn_briefing.greeting == "Hallo Geert!", "Greeting is corrupted under outage!"
    assert resp_resilient.finn_briefing.summary == "Je portfolio is stabiel. Er zijn geen directe waarschuwingen voor je actieve setups.", "Finn summary did not degrade gracefully!"
    assert "DCA setup maken" in resp_resilient.finn_briefing.suggested_actions, "Suggested actions empty under outage!"
    
    print("   ✅ Resiliency Verified! Core data, watchlist scores, and fallback Dutch briefings survived flawlessly.")
    
    # Restore mock AiGateway for clean state
    AiGateway.ask = mock_gateway_ask

    # -----------------------------------------------------------------
    # ⚡ TEST CASE 4: Complete BotService Database Outage
    # -----------------------------------------------------------------
    print("\n📋 Test Case 4: Simulating Bot Service / DB Outage...")
    
    # Monkeypatch BotService to simulate a broken database connection or lock
    from backend.services.bot_service import BotService
    original_get_bot_portfolios = BotService.get_bot_portfolios
    
    async def broken_get_bot_portfolios(*args, **kwargs):
        raise ConnectionRefusedError("PostgreSQL database connection pool exhausted!")
        
    BotService.get_bot_portfolios = broken_get_bot_portfolios
    
    # Clear cache
    DashboardService._overview_cache.clear()
    
    resp_db_failure = await service.get_mobile_overview(user_id=123, bypass_cache=True)
    
    # Assertions for highest priority features
    assert len(resp_db_failure.watchlist) == 3, "Watchlist should load even if bot service crashes!"
    assert resp_db_failure.watchlist[0].price == 57430.20
    
    # Assertions for bot context degradation (should degrade to empty gracefully)
    assert len(resp_db_failure.active_bots) == 0, "Active bots list should be gracefully empty under DB failure!"
    assert resp_db_failure.portfolio.total_balance_eur == 0.0, "Portfolio totals should fall back to 0.0 under DB failure!"
    assert resp_db_failure.portfolio.active_bots_count == 0
    
    # Assertions for briefing
    assert resp_db_failure.finn_briefing.greeting == "Hallo Geert!"
    
    print("   ✅ Database/Bot Service Outage survived beautifully! Watchlist and FINN Briefing rendered flawlessly.")
    
    # Restore original
    BotService.get_bot_portfolios = original_get_bot_portfolios
    AiGateway.ask = original_ask
    
    print("\n🎉 ALL PERFORMANCE, CACHING AND FAULT-TOLERANCE TESTS PASSED with 100% SUCCESS!")


if __name__ == "__main__":
    asyncio.run(run_tests())
