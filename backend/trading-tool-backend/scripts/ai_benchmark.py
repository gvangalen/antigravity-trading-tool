#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🛡️ TRADAMIND AI ASSISTANT REGRESSION BENCHMARK SUITE
Author: Antigravity (Google Deepmind Team)
Created: 2026-05-09

This automated regression testing framework prevents prompt drift, hallucination anomalies,
intent classification regressions, and validates streaming integrity.
"""

import sys
import os
import time
import argparse
import asyncio
import logging
import re
import json
import codecs
from typing import Dict, Any, List, Optional

# Setup path to backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.ai_gateway import AiGateway
from backend.utils.openai_streaming import HardenedStreamingJsonParser

# Disable excessive logging for cleaner CLI output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("ai_benchmark")

BENCHMARK_USER_EMAIL = "benchmark@tradamind.local"

# ANSI colors for premium terminal outputs
COLOR_HEADER = "\033[95m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_BOLD = "\033[1m"
COLOR_UNDERLINE = "\033[4m"
COLOR_END = "\033[0m"

# PRE-DEFINED MOCK DATA FOR SCENARIOS
MOCK_RESPONSES = {
    "TS-01": {
        "text_chunks": ["Hallo! Ik ben de ", "Tradamind AI assistent. ", "Hoe kan ik je vandaag helpen?"],
        "envelope": {
            "response": "Hallo! Ik ben de Tradamind AI assistent. Hoe kan ik je vandaag helpen?",
            "action": None,
            "draft": None,
            "state": {"current_flow": "none", "slots": {}, "status": "none"},
            "reasoning": {
                "confidence_score": 95.0,
                "risk_detected": False,
                "reasons": ["Casual greeting", "Identify assistant"],
                "coaching_level": "beginner"
            }
        }
    },
    "TS-02": {
        "text_chunks": ["De macro trend van ", "Solana (SOL) is momenteel ", "zeer bullish door ", "sterke on-chain volumes."],
        "envelope": {
            "response": "De macro trend van Solana (SOL) is momenteel zeer bullish door sterke on-chain volumes.",
            "action": None,
            "draft": None,
            "state": {"current_flow": "none", "slots": {}, "status": "none"},
            "reasoning": {
                "confidence_score": 88.0,
                "risk_detected": False,
                "reasons": ["Solana on-chain activity", "Volume surge"],
                "coaching_level": "advanced"
            }
        }
    },
    "TS-03": {
        "text_chunks": ["Ik heb een DCA setup ", "voor BTC klaargezet met een ", "frequentie van wekelijks en ", "een interval van 5.0%."],
        "envelope": {
            "response": "Ik heb een DCA setup voor BTC klaargezet met een frequentie van wekelijks en een interval van 5.0%.",
            "action": None,
            "draft": {
                "type": "setup",
                "payload": {
                    "name": "BTC AI DCA",
                    "symbol": "BTC",
                    "setup_type": "dca",
                    "dca_frequency": "weekly",
                    "interval": 5.0
                }
            },
            "state": {"current_flow": "none", "slots": {}, "status": "complete"},
            "reasoning": {
                "confidence_score": 92.0,
                "risk_detected": False,
                "reasons": ["DCA parameters completely gathered", "Formulate draft"],
                "coaching_level": "beginner"
            }
        }
    },
    "TS-04": {
        "text_chunks": ["Ik heb de huidige setup-flow ", "voor je geannuleerd. Je kunt me ", "altijd vragen om iets nieuws te starten!"],
        "envelope": {
            "response": "Ik heb de huidige setup-flow voor je geannuleerd. Je kunt me altijd vragen om iets nieuws te starten!",
            "action": None,
            "draft": None,
            "state": {"current_flow": "none", "slots": {}, "status": "none"},
            "reasoning": None
        }
    },
    "TS-05": {
        "text_chunks": ["Het kopen van BTC is ", "een beslissing die je zorgvuldig moet afwegen. ", "\n\nDisclaimer: Dit is uitsluitend educatieve en analytische informatie, geen direct koop- of verkoopadvies."],
        "envelope": {
            "response": "Het kopen van BTC is een beslissing die je zorgvuldig moet afwegen. \n\nDisclaimer: Dit is uitsluitend educatieve en analytische informatie, geen direct koop- of verkoopadvies.",
            "action": None,
            "draft": None,
            "state": {"current_flow": "none", "slots": {}, "status": "none"},
            "reasoning": {
                "confidence_score": 85.0,
                "risk_detected": True,
                "reasons": ["Aggressive buying trigger moderated", "Safety guardrail disclaimer appended"],
                "coaching_level": "beginner"
            }
        }
    },
    "TS-06": {
        "text_chunks": ["Hoi Henk! Laten we kennismaken en je profiel instellen. ", "Wat is je ervaring met trading (bijv. beginner, advanced, of expert)? ", "En wat is je gewenste risicoprofiel en je beleggingsdoelen?"],
        "envelope": {
            "response": "Hoi Henk! Laten we kennismaken en je profiel instellen. Wat is je ervaring met trading (bijv. beginner, advanced, of expert)? En wat is je gewenste risicoprofiel en je beleggingsdoelen?",
            "action": None,
            "draft": None,
            "state": {
                "current_flow": "user_onboarding",
                "slots": {
                    "experience_level": "beginner",
                    "risk_profile": "balanced",
                    "investment_goals": "steady accumulation"
                },
                "status": "collecting"
            },
            "reasoning": {
                "confidence_score": 98.0,
                "risk_detected": False,
                "reasons": ["Initiating onboarding flow", "Collecting profile slots"],
                "coaching_level": "beginner"
            }
        }
    }
}

async def mock_stream_gpt_json_response(prompt: str, system_role: str):
    matched_scenario = "TS-01"
    
    # Extract original user query to prevent context pollution from system instructions
    query = ""
    for line in prompt.split("\n"):
        if "USER QUERY:" in line:
            query = line.split("USER QUERY:", 1)[1].strip()
            break
            
    q_lower = query.lower() if query else prompt.lower()
    
    if "solana" in q_lower or "sol" in q_lower:
        matched_scenario = "TS-02"
    elif "onboarding" in q_lower or "kennismaken" in q_lower or "profiel" in q_lower:
        matched_scenario = "TS-06"
    elif "annuleer" in q_lower or "wis" in q_lower:
        matched_scenario = "TS-04"
    elif "dca" in q_lower or "interval" in q_lower:
        matched_scenario = "TS-03"
    elif "koop" in q_lower or "buy" in q_lower:
        matched_scenario = "TS-05"

    mock_data = MOCK_RESPONSES[matched_scenario]
    for chunk_text in mock_data["text_chunks"]:
        yield {"event": "text", "data": chunk_text}
        await asyncio.sleep(0.005)  # Fast stream simulation

    yield {"event": "envelope", "data": mock_data["envelope"]}

# ==============================================================================
# 📦 DATABASE SETUP AND SEEDING
# ==============================================================================
async def setup_benchmark_user(db):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(BENCHMARK_USER_EMAIL)
    if not user:
        from backend.utils.auth_utils import hash_password
        password_hash = hash_password("benchmark-super-secret-password-123")
        user = await user_repo.create_user(
            email=BENCHMARK_USER_EMAIL,
            password_hash=password_hash,
            role="user",
            first_name="Benchmark",
            last_name="Runner"
        )
        print(f"{COLOR_BLUE}👤 Brand new benchmark user created: {BENCHMARK_USER_EMAIL}{COLOR_END}")
    
    # Enable is_benchmark_user flag in JSONB field
    user.ai_preferences = {
        "report_style": "professional",
        "tone": "balanced",
        "detail_level": "medium",
        "coaching_style": "constructive",
        "experience_level": "beginner",
        "risk_profile": "balanced",
        "is_benchmark_user": True
    }
    user.ai_requests_limit_day = 5000
    user.ai_requests_used_day = 0
    await db.commit()
    await db.refresh(user)
    return user

async def teardown_benchmark_user(db, user_id):
    from sqlalchemy import text
    # Clean up states and logs for the benchmark user to keep database clean
    await db.execute(text("DELETE FROM conversation_state WHERE user_id = :u_id"), {"u_id": user_id})
    await db.execute(text("DELETE FROM ai_usage_logs WHERE user_id = :u_id"), {"u_id": user_id})
    await db.commit()

# ==============================================================================
# 📡 STREAMING INTEGRITY TESTING
# ==============================================================================
async def run_streaming_integrity_tests():
    print(f"\n{COLOR_HEADER}📦 Running Streaming Integrity Infrastructure Tests...{COLOR_END}")
    
    # 1. UTF-8 multi-byte chunk-boundary splitting test
    print(f"  {COLOR_CYAN}Test 1: Unicode character split over chunk boundaries...{COLOR_END}")
    parser = HardenedStreamingJsonParser()
    smile_char = "😊"  # Bytes: \xf0\x9f\x98\x8a
    part1 = b'{"response": "' + smile_char.encode("utf-8")[:2]
    part2 = smile_char.encode("utf-8")[2:] + b'"}'
    
    tokens = []
    for tok in parser.feed_chunk(part1):
        tokens.append(tok)
    for tok in parser.feed_chunk(part2):
        tokens.append(tok)
        
    full_obj = parser.finalize_and_get_full_object()
    assert smile_char in full_obj.get("response", ""), "Unicode boundary recovery failed!"
    print(f"    {COLOR_GREEN}✅ Passed UTF-8 boundary recovery check.{COLOR_END}")

    # 2. Incomplete and malformed JSON recovery
    print(f"  {COLOR_CYAN}Test 2: Malformed incomplete JSON closure auto-recovery...{COLOR_END}")
    parser_malformed = HardenedStreamingJsonParser()
    incomplete_json = b'{"response": "An incomplete text", "state": {"current_flow": "setup"'
    for _ in parser_malformed.feed_chunk(incomplete_json):
        pass
        
    full_obj_incomplete = parser_malformed.finalize_and_get_full_object()
    assert parser_malformed.parser_recovery_triggered, "Expected parser recovery boolean to trigger!"
    assert full_obj_incomplete.get("response") == "An incomplete text", "Malformed JSON token extraction failed!"
    print(f"    {COLOR_GREEN}✅ Passed Malformed JSON recovery check.{COLOR_END}")

# ==============================================================================
# 🏆 BENCHMARK RUNNER CORE
# ==============================================================================
async def main():
    parser = argparse.ArgumentParser(description="Tradamind AI Assistant Regression Benchmark")
    parser.add_argument("--mock", action="store_true", help="Interceptors enabled. Pre-defined responses will bypass live OpenAI API.")
    parser.add_argument("--fast", action="store_true", help="Runs only fast, non-analytical scenarios (TS-01, TS-04, TS-05).")
    parser.add_argument("--streaming-only", action="store_true", help="Test stream boundaries and parsing parser code without querying LLM.")
    args = parser.parse_args()

    print(f"{COLOR_BOLD}{COLOR_BLUE}🏔️ TRADAMIND AI GATEWAY PHASE 4 BENCHMARK{COLOR_END}")
    
    if args.streaming_only:
        await run_streaming_integrity_tests()
        print(f"\n{COLOR_GREEN}🎉 Stream Integrity validation complete.{COLOR_END}")
        sys.exit(0)

    if args.mock:
        print(f"{COLOR_YELLOW}⚠️  MOCK INTERCEPTORS ENABLED. Bypassing live OpenAI API calls.{COLOR_END}")
        import backend.utils.openai_streaming
        backend.utils.openai_streaming.stream_gpt_json_response = mock_stream_gpt_json_response

    # Load Golden Snapshots
    print(f"\n{COLOR_CYAN}📁 Loading golden-standard snapshot assertions...{COLOR_END}")
    snapshots_dir = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "snapshots")
    snapshots = {}
    
    try:
        for filename in sorted(os.listdir(snapshots_dir)):
            if filename.endswith(".json"):
                path = os.path.join(snapshots_dir, filename)
                with open(path, "r") as f:
                    snap_data = json.load(f)
                    snapshots[snap_data["scenario_id"]] = snap_data
        print(f"    Loaded {len(snapshots)} golden standard scenarios successfully.")
    except Exception as e:
        print(f"❌ Error loading snapshots from {snapshots_dir}: {e}")
        sys.exit(1)

    # Isolate table setup migration in a separate session to prevent transaction abort leaks
    async with async_session_factory() as migration_db:
        from sqlalchemy import text
        try:
            await migration_db.execute(text("""
                CREATE TABLE IF NOT EXISTS conversation_state (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    current_flow VARCHAR,
                    asset VARCHAR,
                    slots JSONB DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # Hotfix: Safely add symbol column to ai_category_insights if it doesn't exist
            await migration_db.execute(text("""
                ALTER TABLE ai_category_insights 
                ADD COLUMN IF NOT EXISTS symbol VARCHAR DEFAULT 'BTC';
            """))
            await migration_db.commit()
        except Exception as migration_err:
            print(f"❌ Primary migration failed: {migration_err}")
            await migration_db.rollback()
            try:
                # Fallback for SQLite or databases without SERIAL/JSONB/Foreign keys syntax
                await migration_db.execute(text("""
                    CREATE TABLE IF NOT EXISTS conversation_state (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        current_flow VARCHAR,
                        asset VARCHAR,
                        slots JSON DEFAULT '{}',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                await migration_db.commit()
            except Exception as sql_err:
                print(f"❌ Secondary migration failed: {sql_err}")
                await migration_db.rollback()

    async with async_session_factory() as db:
        # Setup test environment
        user = await setup_benchmark_user(db)
        
        # Build AiAssistantService
        from backend.infrastructure.repositories.score_repository import ScoreRepository
        from backend.infrastructure.repositories.setup_repository import SetupRepository
        from backend.infrastructure.repositories.report_repository import ReportRepository
        from backend.infrastructure.repositories.bot_repository import BotRepository
        from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
        from backend.infrastructure.repositories.strategy_repository import StrategyRepository
        from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
        from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository

        score_repo = ScoreRepository(db)
        setup_repo = SetupRepository(db)
        report_repo = ReportRepository(db)
        bot_repo = BotRepository(db)
        user_repo = UserRepository(db)
        market_data_repo = MarketDataRepository(db)
        strategy_repo = StrategyRepository(db)
        state_repo = ConversationStateRepository(db)
        context_repo = AssistantContextRepository(db)
        ai_gateway = AiGateway(user_repo, score_repo)

        service = AiAssistantService(
            score_repo, setup_repo, report_repo, bot_repo, user_repo,
            market_data_repo, strategy_repo, state_repo, ai_gateway, context_repo
        )

        scenarios_to_run = ["TS-01", "TS-02", "TS-03", "TS-04", "TS-05", "TS-06"]
        if args.fast:
            scenarios_to_run = ["TS-01", "TS-04", "TS-05", "TS-06"]
            print(f"{COLOR_YELLOW}⚡ Fast mode enabled. Running scenarios: {scenarios_to_run}{COLOR_END}")

        results = []
        overall_start = time.perf_counter()

        for scenario_id in scenarios_to_run:
            snap = snapshots.get(scenario_id)
            if not snap:
                print(f"❌ Snapshot for {scenario_id} missing. Skipping.")
                continue

            print(f"\n{COLOR_BOLD}{COLOR_BLUE}----------------------------------------------------------------------{COLOR_END}")
            print(f"🎬 Running {COLOR_BOLD}{scenario_id}{COLOR_END}: {COLOR_CYAN}\"{snap['query']}\"{COLOR_END}")
            
            # Setup/Reset state before running scenario
            await teardown_benchmark_user(db, user.id)

            start_t = time.perf_counter()
            response_text = ""
            final_envelope = None
            
            try:
                # Stream the response End-to-End to check both character and terminal JSON packets
                async for chunk in service.get_chat_response_stream(
                    user_id=user.id,
                    user_query=snap["query"],
                    history=[],
                    context_data={"symbol": "GLOBAL"}
                ):
                    if chunk["event"] == "text":
                        response_text += chunk["data"]
                    elif chunk["event"] == "envelope":
                        final_envelope = chunk["data"]

                duration_ms = (time.perf_counter() - start_t) * 1000
                print(f"⏱️  Execution completed in {duration_ms:.2f}ms")
                
                # Assertions block
                assertions = snap["assertions"]
                failures = []

                # 1. Intent Validation
                intent = service._classify_intent(snap["query"])
                if assertions.get("intent") and intent != assertions["intent"]:
                    failures.append(f"Intent mismatch: Classified as '{intent}', expected '{assertions['intent']}'")

                # 2. Strict String Negatives (e.g. formatting and safety guardrails checks)
                for term in assertions.get("must_not_contain", []):
                    if term.lower() in response_text.lower():
                        failures.append(f"Safety Violation: Response contains forbidden phrase '{term}'")

                # 3. Fuzzy String Match Positives
                for term in assertions.get("must_contain", []):
                    if term.lower() not in response_text.lower():
                        failures.append(f"Formatting Drift: Response missing expected keyword '{term}'")

                # 4. Latency Threshold Checks (especially for Abort engine bypass validation)
                if assertions.get("max_duration_ms") and duration_ms > assertions["max_duration_ms"]:
                    failures.append(f"Performance Regression: Latency is {duration_ms:.1f}ms, expected limit is {assertions['max_duration_ms']}ms")

                # 5. Envelope structures & consistency check
                if final_envelope:
                    reasoning = final_envelope.get("reasoning")
                    
                    if assertions.get("must_contain_reasoning") and not reasoning:
                        failures.append("Explainability Regression: Expecting a Reasoning CoT block, got None")
                    
                    if reasoning:
                        conf = reasoning.get("confidence_score") or 0.0
                        if assertions.get("min_confidence_score") and conf < assertions["min_confidence_score"]:
                            failures.append(f"Factual Drift: Confidence score is {conf}%, expecting min {assertions['min_confidence_score']}%")
                    
                    if assertions.get("must_have_draft") and not final_envelope.get("draft"):
                        failures.append("Draftcard regression: Expected draft parameters, got None")
                        
                    draft_fields = assertions.get("draft_fields")
                    if draft_fields and final_envelope.get("draft"):
                        payload = final_envelope["draft"].get("payload", {})
                        for k, v in draft_fields.items():
                            val = payload.get(k)
                            if val is None and k == "pair":
                                val = payload.get("symbol")
                            if str(val).lower() != str(v).lower():
                                failures.append(f"Slot-filling mismatch on slot '{k}': got '{val}', expected '{v}'")

                    if assertions.get("must_have_state") and not final_envelope.get("state"):
                        failures.append("State regression: Expected conversation state parameters, got None")
                        
                    if assertions.get("state_current_flow") and final_envelope.get("state"):
                        curr_flow = final_envelope["state"].get("current_flow")
                        if curr_flow != assertions["state_current_flow"]:
                            failures.append(f"State flow mismatch: got '{curr_flow}', expected '{assertions['state_current_flow']}'")

                    action_payload = final_envelope.get("action")
                    if action_payload and action_payload.get("type") == "navigate_to_page":
                        path = action_payload.get("params", {}).get("path")
                        if path:
                            base_path = path.split("?")[0]
                            ALLOWED_PATHS = ["/dashboard", "/macro", "/technical", "/bot", "/strategy", "/setup", "/report", "/profile"]
                            if base_path not in ALLOWED_PATHS:
                                failures.append(f"Action Security Violation: Unauthorized navigate_to_page base path '{base_path}'")

                else:
                    failures.append("No envelope was returned in the stream stream events!")

                if failures:
                    print(f"🔴 {COLOR_RED}{COLOR_BOLD}TS-FAIL: {COLOR_END} {len(failures)} assertion failures detected:")
                    for f_msg in failures:
                        print(f"   - {COLOR_RED}{f_msg}{COLOR_END}")
                    results.append({"id": scenario_id, "pass": False, "failures": failures, "latency": duration_ms})
                else:
                    print(f"🟢 {COLOR_GREEN}{COLOR_BOLD}TS-PASS: {COLOR_END} Scenario passed all golden-assertions successfully.")
                    results.append({"id": scenario_id, "pass": True, "failures": [], "latency": duration_ms})

            except Exception as sex:
                print(f"💥 {COLOR_RED}CRASH: Failed to run scenario {scenario_id} due to code crash: {sex}{COLOR_END}")
                results.append({"id": scenario_id, "pass": False, "failures": [f"Crash: {sex}"], "latency": 0.0})

        # Run streaming integrity tests
        await run_streaming_integrity_tests()

        # Teardown
        await teardown_benchmark_user(db, user.id)

        # Print Final CLI Dashboard Summary
        total_time = time.perf_counter() - overall_start
        passed_scenarios = [r for r in results if r["pass"]]
        failed_scenarios = [r for r in results if not r["pass"]]
        avg_lat = sum(r["latency"] for r in results) / len(results) if results else 0

        print(f"\n{COLOR_BOLD}{COLOR_BLUE}======================================================================{COLOR_END}")
        print(f"🏆 {COLOR_BOLD}FINAL BENCHMARK SUMMARY{COLOR_END}")
        print(f"======================================================================{COLOR_END}")
        print(f"📊 Runs: {COLOR_CYAN}{len(results)} total scenarios executed{COLOR_END}")
        print(f"🟢 Passes: {COLOR_GREEN}{len(passed_scenarios)}{COLOR_END}")
        print(f"🔴 Fails: {COLOR_RED}{len(failed_scenarios)}{COLOR_END}")
        print(f"⏱️  Average Latency: {COLOR_YELLOW}{avg_lat:.2f} ms{COLOR_END}")
        print(f"🚀 Total Duration: {COLOR_CYAN}{total_time:.2f} seconds{COLOR_END}")
        print(f"{COLOR_BOLD}{COLOR_BLUE}======================================================================{COLOR_END}")

        if failed_scenarios:
            print(f"\n🚨 {COLOR_RED}{COLOR_BOLD}REGRESSION DETECTED!{COLOR_END} Some golden assertions failed. Please inspect traces above.")
            sys.exit(1)
        else:
            print(f"\n✨ {COLOR_GREEN}{COLOR_BOLD}ALL SYSTEMS STABLE!{COLOR_END} Tradamind AI Assistant conforms perfectly to golden snapshots.")
            sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
