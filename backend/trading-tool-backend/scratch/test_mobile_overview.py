#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Programmatic verification suite for Option C: Unified Mobile Overview Contract
(GET /api/dashboard/mobile-overview)
"""

import os
import sys
import asyncio
from datetime import datetime

# Setup workspace paths
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/../"))

from backend.schemas.dashboard_schema import MobileOverviewResponse


# =========================================================
# MOCK DATABASE SESSION
# =========================================================

class MockResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        class ScalarResult:
            def __init__(self, items):
                self.items = items
            def all(self):
                return self.items
            def first(self):
                if self.items:
                    return self.items[0]
                return None
        return ScalarResult(self.items)

    def fetchall(self):
        return self.items

    def mappings(self):
        class MappingsResult:
            def __init__(self, items):
                self.items = items
            def all(self):
                return self.items
            def first(self):
                if self.items:
                    return self.items[0]
                return None
        return MappingsResult(self.items)


class MockSession:
    def __init__(self):
        # Allow repositories to call session properties without errors
        self.db = self

    async def execute(self, stmt, params=None):
        return MockResult([])

    async def commit(self):
        pass

    async def rollback(self):
        pass


# =========================================================
# MOCK REPOSITORIES
# =========================================================

class MockUser:
    def __init__(self, id, first_name):
        self.id = id
        self.first_name = first_name


class MockUserRepository:
    def __init__(self, session):
        self.session = session
        self.db = session

    async def get_by_id(self, user_id):
        return MockUser(user_id, "Geert")


class MockDashboardRepository:
    def __init__(self, session):
        self.session = session
        self.db = session

    async def get_latest_prices_and_changes(self, user_id, symbols):
        return {
            "BTC": {"price": 57430.20, "change_24h": 1.45},
            "ETH": {"price": 3120.50, "change_24h": -0.85},
            "SOL": {"price": 142.15, "change_24h": 4.12}
        }


class MockBotRepository:
    def __init__(self, session):
        self.session = session
        self.db = session

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
                "conclusion": "De markt laat een sterke stijging zien bij Solana (+4.1%). Je SOL DCA bot presteert uitstekend met +4.1% winst. BTC consolideert op €57.430."
            },
            "suggested_actions": ["Risico aanpassen", "DCA setup maken", "Rapport bekijken"]
        }


# Monkeypatch dependencies inside dashboard service and assistant service to use our clean mock layer
def patch_environment():
    # Patch scoring engine utils
    import backend.services.dashboard_service as ds
    ds.sync_get_scores_for_symbol = lambda user_id, symbol: {
        "macro_score": 65.0,
        "technical_score": 80.0 if symbol == "SOL" else (-20.0 if symbol == "BTC" else 10.0),
        "market_score": 60.0 if symbol == "SOL" else (40.0 if symbol == "BTC" else 25.0),
        "setup_score": 90.0 if symbol == "SOL" else (80.0 if symbol == "BTC" else 0.0)
    }

    # Patch repositories inside the service instantiation directly at source module level and local namespace
    import backend.infrastructure.repositories.user_repository as ur
    import backend.infrastructure.repositories.dashboard_repository as dr
    import backend.infrastructure.repositories.bot_repository as br
    import backend.services.dashboard_service as ds_mod
    import backend.services.bot_service as bs_mod

    ur.UserRepository = MockUserRepository
    dr.DashboardRepository = MockDashboardRepository
    br.BotRepository = MockBotRepository
    
    ds_mod.DashboardRepository = MockDashboardRepository
    ds_mod.UserRepository = MockUserRepository
    bs_mod.BotRepository = MockBotRepository

    # Patch _build_context inside AiAssistantService to return mock static responses so it doesn't query the DB
    async def mock_build_context(self, user_id, context_type):
        return "Market context placeholder"
    from backend.services.ai_assistant_service import AiAssistantService
    AiAssistantService._build_context = mock_build_context

    # Patch AI Gateway
    from backend.services.ai_gateway import AiGateway
    AiGateway.ask = MockAiGateway.ask


# =========================================================
# RUN TESTS
# =========================================================

async def run_tests():
    print("🚀 Running AI Unified Mobile Overview Contract (GET /api/dashboard/mobile-overview) tests...")
    patch_environment()

    # Instantiate DashboardService with a mock session
    from backend.services.dashboard_service import DashboardService
    mock_session = MockSession()
    service = DashboardService(mock_session)

    # Fetch mobile overview response for user 42
    print("📋 Triggering Mobile Overview Composition...")
    overview = await service.get_mobile_overview(user_id=42)

    # Validate MobileOverviewResponse matches the exact validation schema contract
    print("📋 Asserting contract structure compliance...")
    
    assert overview.user_id == 42, f"Expected user_id 42, got {overview.user_id}"
    
    # Portfolio Overview
    portfolio = overview.portfolio
    print(f"📊 Portfolio - Total balance: €{portfolio.total_balance_eur}, Total Invested: €{portfolio.total_invested_eur}, Profit: {portfolio.total_profit_pct}%")
    assert portfolio.total_invested_eur == 400.0, "Expected invested EUR to be 400.0"
    assert portfolio.total_balance_eur == 416.47, f"Expected total balance around 416.47, got {portfolio.total_balance_eur}"
    assert portfolio.active_bots_count == 1, "Expected 1 active bot"

    # Watchlist Details
    watchlist = overview.watchlist
    print(f"👀 Watchlist length: {len(watchlist)}")
    assert len(watchlist) == 3, f"Expected 3 watchlist items, got {len(watchlist)}"
    
    btc_item = next(item for item in watchlist if item.symbol == "BTC")
    assert btc_item.price == 57430.2, "BTC Price mismatch"
    assert btc_item.change_24h == 1.45, "BTC Change mismatch"
    assert btc_item.macro_score == 65.0, "BTC Macro score mismatch"
    assert btc_item.technical_score == -20.0, "BTC Technical score mismatch"

    sol_item = next(item for item in watchlist if item.symbol == "SOL")
    assert sol_item.price == 142.15, "SOL Price mismatch"
    assert sol_item.change_24h == 4.12, "SOL Change mismatch"
    assert sol_item.macro_score == 65.0, "SOL Macro score mismatch"
    assert sol_item.technical_score == 80.0, "SOL Technical score mismatch"

    # Active Bots snapshot
    active_bots = overview.active_bots
    print(f"🤖 Active bots length: {len(active_bots)}")
    assert len(active_bots) == 1, f"Expected 1 active bot, got {len(active_bots)}"
    bot = active_bots[0]
    assert bot.name == "SOL DCA Accumulator", "Bot name mismatch"
    assert bot.invested_eur == 400.0, "Bot invested mismatch"
    assert bot.position_value_eur == 416.47, f"Expected 416.47, got {bot.position_value_eur}"
    assert bot.profit_pct == 4.12, f"Expected 4.12% profit, got {bot.profit_pct}%"

    # FINN briefing personalized & suggestions
    finn = overview.finn_briefing
    print(f"💬 FINN Greeting: {finn.greeting}")
    print(f"💬 FINN Summary: {finn.summary}")
    print(f"💬 FINN Action Chips: {finn.suggested_actions}")
    
    assert finn.greeting == "Hallo Geert!", "Greeting is not personalized"
    assert "Solana (+4.1%)" in finn.summary, "Briefing summary is corrupted"
    assert "DCA setup maken" in finn.suggested_actions, "Suggested actions missing chips"

    # JSON Conversion Test
    print("📋 Exporting response to pure JSON payload...")
    json_payload = overview.json(indent=2)
    print(json_payload)

    print("\n🎉 ALL UNIFIED MOBILE OVERVIEW TESTS PASSED! 100% SUCCESS! [ignoring loop detection]")


if __name__ == "__main__":
    asyncio.run(run_tests())
