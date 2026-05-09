import logging
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Union, Tuple, List

from backend.utils.openai_client import ask_gpt_text_async, ask_gpt_json_async
from backend.utils.ai_cost_calculator import calculate_cost
from backend.utils.embedding_client import get_embedding
from backend.infrastructure.vector_store import get_vector_store
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from sqlalchemy import text

logger = logging.getLogger(__name__)

# TTL Config (in minutes)
TTL_CONFIG = {
    "assistant": 60,
    "macro": 180,
    "market": 180,
    "technical": 180,
    "report": 1440,
    "strategy": 1440,
    "default": 180
}

class AiGateway:
    def __init__(self, user_repo: UserRepository, score_repo: ScoreRepository):
        self.user_repo = user_repo
        self.score_repo = score_repo
        self.vector_store = get_vector_store()

    def _normalize_query(self, query: str) -> str:
        return query.strip().lower()

    async def ask(
        self, 
        user_id: int, 
        prompt: str, 
        system_role: str, 
        mode: str = "text", 
        schema: Optional[Dict[str, Any]] = None,
        purpose: str = "assistant",
        symbol: str = "GLOBAL",
        timeframe: str = "1H",
        user_model: Optional[Any] = None
    ) -> Union[str, Dict[str, Any]]:
        """
        De centrale toegangspoort voor AI-aanvragen. 
        Handelt quotas, caching (Exact & Semantic) en fallbacks af met context-matching.
        """
        start_time = time.perf_counter()
        norm_query = self._normalize_query(prompt)
        query_hash = hashlib.sha256(norm_query.encode()).hexdigest()
        
        # 1. STEP 1: Exact Match (Context Aware)
        exact_hit = await self._check_exact_match(query_hash, symbol, timeframe, purpose)
        if exact_hit:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            response, cost, age = exact_hit
            logger.info(f"🚀 [Ai-Gateway] EXACT HIT voor {user_id} ({duration_ms}ms)")
            
            await self._log_usage(
                user_id=user_id, model="cache_exact", p_tokens=0, c_tokens=0, 
                cost=0.0, purpose=purpose, status="cache_exact",
                response_time_ms=duration_ms, estimated_cost_if_full=cost,
                cache_age_seconds=age, symbol=symbol
            )
            return response
            
        # 2. STEP 2: Semantic Match (Only for non-trading, non-assistant categories)
        not_allowed_semantic = ["trading_signal", "entry_exit", "live_price", "assistant"]
        if purpose not in not_allowed_semantic:
            semantic_hit = await self._check_semantic_match(norm_query, symbol, timeframe, purpose)
            if semantic_hit:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                response, cost, score, age = semantic_hit
                logger.info(f"🧠 [Ai-Gateway] SEMANTIC HIT (Score: {score:.4f}) voor {user_id} ({duration_ms}ms)")
                
                await self._log_usage(
                    user_id=user_id, model="cache_semantic", p_tokens=0, c_tokens=0, 
                    cost=0.0, purpose=purpose, status="cache_semantic",
                    response_time_ms=duration_ms, estimated_cost_if_full=cost,
                    similarity_score=score, cache_age_seconds=age, symbol=symbol
                )
                return response
                
        # 3. Get User & Quota State
        if user_model is not None:
            user = user_model
        else:
            user = await self.user_repo.get_by_id(user_id)
            
        if not user: return "Gebruiker niet gevonden."
        
        limit = getattr(user, "ai_requests_limit_day", 25) or 25
        used = getattr(user, "ai_requests_used_day", 0) or 0
        
        # 4. Quota Check -> Fallback
        if used >= limit:
            res = await self._handle_fallback(user_id, prompt, mode)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            await self._log_usage(
                user_id=user_id, model="fallback", p_tokens=0, c_tokens=0, 
                cost=0.0, purpose=purpose, status="fallback", response_time_ms=duration_ms, symbol=symbol
            )
            return res
            
        # 5. STEP 3: Full AI Call
        res = await self._execute_ai_call(
            user_id, prompt, norm_query, system_role, mode, schema, 
            purpose, symbol, timeframe, start_time=start_time
        )
        return res


    async def _check_exact_match(self, query_hash: str, symbol: str, timeframe: str, category: str) -> Optional[Tuple[Any, float, int]]:
        stmt = text("""
            SELECT response_json, original_cost, created_at, ttl_minutes 
            FROM ai_response_cache 
            WHERE query_hash = :h AND symbol = :s AND timeframe = :t AND category = :c
            LIMIT 1
        """)
        res = await self.user_repo.db.execute(stmt, {"h": query_hash, "s": symbol, "t": timeframe, "c": category})
        row = res.mappings().first()
        
        if row:
            expiry = row['created_at'] + timedelta(minutes=row['ttl_minutes'])
            age = int((datetime.utcnow() - row['created_at']).total_seconds())
            if datetime.utcnow() < expiry:
                return (row["response_json"], float(row["original_cost"] or 0), age)
            else:
                logger.info(f"⏳ [Ai-Gateway] Exact cache expired for {query_hash}")
        return None

    async def _check_semantic_match(self, query: str, symbol: str, timeframe: str, category: str) -> Optional[Tuple[Any, float, float, int]]:
        # 1. Get embedding
        emb = get_embedding(query)
        if not emb: return None
        
        # 2. Search FAISS
        matches = self.vector_store.search(emb, top_k=1)
        if not matches: return None
        
        query_hash, score = matches[0]
        
        # 3. Rule Check: Similarity >= 0.92
        if score < 0.92:
            return None
            
        # 4. Logic Match in DB (Enforce Context)
        stmt = text("""
            SELECT response_json, original_cost, created_at, ttl_minutes, symbol, timeframe, category
            FROM ai_response_cache 
            WHERE query_hash = :h LIMIT 1
        """)
        res = await self.user_repo.db.execute(stmt, {"h": query_hash})
        row = res.mappings().first()
        
        if row:
            # Strikte Context Check
            if row['symbol'] != symbol or row['timeframe'] != timeframe or row['category'] != category:
                return None # Context mismatch
                
            expiry = row['created_at'] + timedelta(minutes=row['ttl_minutes'])
            age = int((datetime.utcnow() - row['created_at']).total_seconds())
            
            if datetime.utcnow() < expiry:
                return (row["response_json"], float(row["original_cost"] or 0), float(score), age)
                
        return None

    async def _execute_ai_call(
        self, user_id: int, original_prompt: str, norm_query: str, 
        system_role: str, mode: str, schema: Optional[Dict[str, Any]], 
        purpose: str, symbol: str, timeframe: str, start_time: float
    ):
        if mode == "json":
            result = await ask_gpt_json_async(prompt=original_prompt, system_role=system_role, schema=schema)
            usage = result.pop("_usage", {}) if isinstance(result, dict) else {}
            content = result
        else:
            # ask_gpt_text returns a simple string, so we mock the usage to prevent crashes
            content = await ask_gpt_text_async(prompt=original_prompt, system_role=system_role)
            usage = {} 

        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        model = usage.get("model", "gpt-4o-mini")
        
        cost = calculate_cost(model, p_tokens, c_tokens)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        await self.user_repo.update_ai_usage(user_id, 1, cost, p_tokens + c_tokens)
        
        await self._log_usage(
            user_id, model, p_tokens, c_tokens, cost, purpose, "full_ai", 
            response_time_ms=duration_ms, estimated_cost_if_full=cost, symbol=symbol
        )
        
        # 6. Save to Cache & Index
        ttl = TTL_CONFIG.get(purpose, TTL_CONFIG["default"])
        query_hash = hashlib.sha256(norm_query.encode()).hexdigest()
        
        # Get embedding logic for indexing
        emb = get_embedding(norm_query)
        
        await self._save_cache(
            query_hash=query_hash, 
            text_query=original_prompt, 
            norm_query=norm_query,
            response=content, 
            cost=cost,
            symbol=symbol,
            timeframe=timeframe,
            category=purpose,
            ttl=ttl,
            embedding=emb
        )
        
        # Update Vector Store index
        if emb:
            self.vector_store.add(query_hash, emb)

        return content

    async def _handle_fallback(self, user_id: int, prompt: str, mode: str) -> Union[str, Dict[str, Any]]:
        global_macro = await self.score_repo.get_global_insight("macro")
        summary = global_macro.get("summary") if global_macro else "De markt is momenteel in beweging."
        msg = f"Inzicht van de Global Intelligence Layer: {summary}\n\n(Opmerking: Je hebt je dagelijkse AI-limiet bereikt.)"
        if mode == "json":
            return {
                "greeting": "Hoi!",
                "bot_insight": {
                    "conclusion": "AI-limiet bereikt",
                    "action": "Check dashboard",
                    "why": "Je hebt je dagelijkse limiet aan AI-aanvragen bereikt."
                },
                "market_insight": {
                    "conclusion": "Intelligence Layer is standby.",
                    "action": "Bekijk live charts",
                    "why": "Inzichten zijn gepauzeerd wegens de limiet."
                }
            }
        return msg

    async def _save_cache(self, query_hash: str, text_query: str, norm_query: str, response: Any, cost: float, symbol: str, timeframe: str, category: str, ttl: int, embedding: Optional[List[float]]):
        try:
            stmt = text("""
                INSERT INTO ai_response_cache (query_hash, query_text, normalized_query, response_json, original_cost, symbol, timeframe, category, ttl_minutes, embedding, created_at)
                VALUES (:h, :t, :nt, :r, :c, :s, :tf, :cat, :ttl, :emb, :now)
                ON CONFLICT (query_hash) DO UPDATE SET 
                    response_json = EXCLUDED.response_json,
                    original_cost = EXCLUDED.original_cost,
                    created_at = EXCLUDED.created_at,
                    embedding = EXCLUDED.embedding
            """)
            await self.user_repo.db.execute(stmt, {
                "h": query_hash, "t": text_query, "nt": norm_query, "r": json.dumps(response), 
                "c": cost, "s": symbol, "tf": timeframe, "cat": category, "ttl": ttl,
                "emb": json.dumps(embedding) if embedding else None, "now": datetime.utcnow()
            })
            await self.user_repo.db.commit()
        except Exception as e:
            logger.error(f"❌ Cache save error: {e}")

    async def _log_usage(
        self, user_id: int, model: str, p_tokens: int, c_tokens: int, 
        cost: float, purpose: str, status: str, 
        response_time_ms: int = 0, estimated_cost_if_full: float = 0.0,
        similarity_score: float = None, cache_age_seconds: int = None,
        rejected_reason: str = None, symbol: str = "GLOBAL"
    ):
        try:
            stmt = text("""
                INSERT INTO ai_usage_logs (user_id, model, prompt_tokens, completion_tokens, cost, purpose, status, response_time_ms, estimated_cost_if_full, similarity_score, cache_age_seconds, rejected_reason, symbol)
                VALUES (:u, :m, :p, :c, :co, :pur, :s, :rt, :ec, :ss, :cas, :rr, :sym)
            """)
            await self.user_repo.db.execute(stmt, {
                "u": user_id, "m": model, "p": p_tokens, "c": c_tokens, "co": cost, "pur": purpose, "s": status,
                "rt": response_time_ms, "ec": estimated_cost_if_full, "ss": similarity_score, "cas": cache_age_seconds, "rr": rejected_reason,
                "sym": symbol
            })
            await self.user_repo.db.commit()
        except Exception as e:
            logger.error(f"❌ AI usage logging error (non-blocking fallback): {e}")
            try:
                await self.user_repo.db.rollback()
            except Exception:
                pass
