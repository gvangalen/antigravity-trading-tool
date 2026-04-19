import asyncio
import logging
import sys
import os
import json
import time

# Logging minimal for stress
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("STRESS_TEST")

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.ai_gateway import AiGateway

# SCENARIO Definitions
BTC_BASELINE = [
    "What is the role of a stop loss in a BTC trade?",
    "Explain the importance of trend following for Bitcoin.",
    "How does leverage affect risk in BTC scalp trades?",
    "What are support and resistance levels for BTC?",
    "Explain the relationship between BTC volume and price action.",
    "Why is position sizing critical for Bitcoin traders?",
    "What is a trailing stop and how to use it on BTC?",
    "Explain the concept of risk-to-reward ratio for BTC.",
    "How do moving averages help in BTC trend identification?",
    "What is the impact of BTC halving on trading strategies?"
]

# Semantically similar but differently worded
BTC_SEMANTIC = [
    "Explain the function of stop losses when trading BTC.",
    "Tell me why following trends is key for Bitcoin trading.",
    "How is risk impacted by leverage in Bitcoin scalping?",
    "What do support/resistance zones mean for BTC traders?",
    "Describe how Bitcoin volume relates to its price movements.",
    "Why must Bitcoin traders care about sizing their positions?",
    "Tell me about using trailing stops on BTC trades.",
    "What's the meaning of risk/reward ratio for Bitcoin?",
    "Can moving averages assist in identifying BTC trends?",
    "How does the Bitcoin halving event change trading plans?"
]

async def stress_test():
    print("🚀 Starting Phase 3 LAUNCH READINESS STRESS TEST...")
    
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        score_repo = ScoreRepository(session)
        gateway = AiGateway(user_repo, score_repo)

        user_id = 30 # Henk
        results = []

        # ---------------------------------------------------------
        # SCENARIO 1: Baseline BTC (10 Full Calls)
        # ---------------------------------------------------------
        print("\n[1] SCENARIO: BTC Baseline (10 unique questions)...")
        for q in BTC_BASELINE:
            print(f" > Call: {q[:30]}...")
            res = await gateway.ask(user_id, q, "Expert", purpose="assistant", symbol="BTC/USDT")
            results.append({"type": "baseline", "q": q, "symbol": "BTC/USDT"})

        # ---------------------------------------------------------
        # SCENARIO 2: Semantic BTC (10 Semantic Hits)
        # ---------------------------------------------------------
        print("\n[2] SCENARIO: BTC Semantic (10 rephrased questions)...")
        for q in BTC_SEMANTIC:
            print(f" > Call: {q[:30]}...")
            res = await gateway.ask(user_id, q, "Expert", purpose="assistant", symbol="BTC/USDT")
            results.append({"type": "semantic", "q": q, "symbol": "BTC/USDT"})

        # ---------------------------------------------------------
        # SCENARIO 3: Exact BTC (10 Exact Hits)
        # ---------------------------------------------------------
        print("\n[3] SCENARIO: BTC Exact (10 identical repeats)...")
        for q in BTC_BASELINE:
            print(f" > Call: {q[:30]}...")
            res = await gateway.ask(user_id, q, "Expert", purpose="assistant", symbol="BTC/USDT")
            results.append({"type": "exact", "q": q, "symbol": "BTC/USDT"})

        # ---------------------------------------------------------
        # SCENARIO 4: Context Isolation (20 Calls ETH/SOL)
        # ---------------------------------------------------------
        print("\n[4] SCENARIO: Context Isolation (ETH + SOL)...")
        for asset in ["ETH/USDT", "SOL/USDT"]:
            print(f" >> Processing {asset}...")
            for q in BTC_BASELINE[:10]:
                print(f"  > Call: {q[:30]}...")
                res = await gateway.ask(user_id, q, "Expert", purpose="assistant", symbol=asset)
                results.append({"type": f"context_{asset}", "q": q, "symbol": asset})

        # ---------------------------------------------------------
        # SCENARIO 5: Limit Test (5 calls beyond 50)
        # ---------------------------------------------------------
        print("\n[5] SCENARIO: Gateway Limit Test (forcing >50 calls)...")
        for i in range(5):
            q = f"Question beyond limit {i}?"
            print(f" > Call: {q}")
            res = await gateway.ask(user_id, q, "Expert", purpose="assistant", symbol="BTC/USDT")
            results.append({"type": "beyond_limit", "q": q, "symbol": "BTC/USDT"})

    print("\n🏁 STRESS TEST COMPLETED.")

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    asyncio.run(stress_test())
