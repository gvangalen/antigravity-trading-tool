import logging
import asyncio
import json
from datetime import date, timedelta, datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.bot_schema import (
    BotConfigCreateSchema,
    BotConfigUpdateSchema,
    BotManualOrderSchema,
    TradePlanUpsertSchema
)
from backend.infrastructure.repositories.bot_repository import BotRepository

logger = logging.getLogger(__name__)

# =========================================================
# SYNCHRONOUS WRAPPERS FOR LEGACY COMPONENTS/AGENTS
# =========================================================
def sync_snapshot_all_for_user(user_id: int):
    from backend.services.portfolio_snapshot_service import snapshot_all_for_user
    snapshot_all_for_user(user_id, bucket="1h")
    snapshot_all_for_user(user_id, bucket="1d")

def sync_run_daily_strategy_snapshot(user_id: int):
    from backend.celery_task.strategy_task import run_daily_strategy_snapshot
    run_daily_strategy_snapshot(user_id=user_id)

def sync_run_trading_bot_agent(user_id: int, report_date: date, bot_id: int):
    from backend.ai_agents.trading_bot_agent import run_trading_bot_agent
    return run_trading_bot_agent(user_id=user_id, report_date=report_date, bot_id=bot_id)

def sync_execute_manual_decision(user_id: int, bot_id: int, decision_id: int):
    from backend.utils.db import get_db_connection
    from backend.ai_agents.trading_bot_agent import execute_manual_decision
    
    conn = get_db_connection()
    try:
        execute_manual_decision(
            conn=conn, user_id=user_id, bot_id=bot_id, decision_id=decision_id
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

class BotService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = BotRepository(db_session)

    def _safe_json(self, v, fallback):
        if v is None:
            return fallback
        if isinstance(v, (dict, list)):
            return v
        try:
            return json.loads(v)
        except Exception:
            return fallback

    # ==========================
    # BOT CONFIGS
    # ==========================
    async def get_bot_configs(self, user_id: int) -> List[dict]:
        rows = await self.repository.get_bot_configs(user_id)
        out = []
        for r in rows:
            strategy = None
            if r.get("strategy_id"):
                strategy = {
                    "id": r["strategy_id"],
                    "setup_type": r["setup_type"],
                    "name": r["strategy_name"],
                    "setup": {
                        "id": r["setup_id"],
                        "name": r["setup_name"],
                        "symbol": r["symbol"],
                        "timeframe": r["timeframe"],
                    },
                }
            out.append({
                "id": r["id"],
                "name": r["name"],
                "is_active": bool(r["is_active"]),
                "is_live": bool(r["is_live"]),
                "mode": r["mode"],
                "cadence": r["cadence"],
                "risk_profile": r["risk_profile"] or "balanced",
                "last_run": r["last_run"].isoformat() if r.get("last_run") else None,
                "budget": {
                    "total_eur": float(r["budget_total_eur"] or 0),
                    "daily_limit_eur": float(r["budget_daily_limit_eur"] or 0),
                    "min_order_eur": float(r["budget_min_order_eur"] or 0),
                    "max_order_eur": float(r["budget_max_order_eur"] or 0),
                    "max_asset_exposure_pct": float(r["max_asset_exposure_pct"] or 100),
                },
                "strategy": strategy,
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            })
        return out

    async def create_bot_config(self, payload: BotConfigCreateSchema, user_id: int) -> dict:
        data = payload.dict()
        data["user_id"] = user_id
        bot_id = await self.repository.create_bot_config(data)
        await self.session.commit()
        return {"ok": True, "id": bot_id}

    async def update_bot_config(self, bot_id: int, payload: BotConfigUpdateSchema, user_id: int) -> dict:
        updates = payload.dict(exclude_unset=True)
        # Handle aliases
        if "total_eur" in updates: updates["budget_total_eur"] = updates.pop("total_eur")
        if "daily_limit_eur" in updates: updates["budget_daily_limit_eur"] = updates.pop("daily_limit_eur")
        if "min_order_eur" in updates: updates["budget_min_order_eur"] = updates.pop("min_order_eur")
        if "max_order_eur" in updates: updates["budget_max_order_eur"] = updates.pop("max_order_eur")
        
        updated_id = await self.repository.update_bot_config(user_id, bot_id, updates)
        if not updated_id:
            raise HTTPException(404, "Bot niet gevonden")
            
        await self.session.commit()
        return {"ok": True, "bot_id": bot_id}

    async def delete_bot_config(self, bot_id: int, user_id: int) -> dict:
        deleted = await self.repository.delete_bot_config(user_id, bot_id)
        if not deleted:
            raise HTTPException(404, "Bot niet gevonden")
        await self.session.commit()
        return {"ok": True, "bot_id": bot_id, "deleted": True}

    # ==========================
    # BOT DECISIONS (TODAY/HISTORY)
    # ==========================
    async def get_bot_today(self, user_id: int) -> dict:
        today = date.today()
        daily_scores = await self.repository.get_daily_scores_row(user_id, today) or {
            "macro": 10, "technical": 10, "market": 10, "setup": 10
        }
        
        bot_rows = await self.repository.get_active_bots_with_setups(user_id)
        if not bot_rows:
            return {"date": str(today), "scores": daily_scores, "decisions": [], "orders": [], "executions": []}
            
        bots_by_id = {
            int(r["id"]): {
                "bot_id": int(r["id"]), "bot_name": r["name"], "symbol": r["symbol"], 
                "timeframe": r["timeframe"], "setup_type": r["setup_type"], "setup_name": r["setup_name"]
            } for r in bot_rows
        }
        
        decision_rows = await self.repository.get_bot_decisions_by_date(user_id, today)
        decisions_by_bot = {}
        
        for r in decision_rows:
            bot_id = int(r["bot_id"])
            if bot_id in decisions_by_bot: continue
            bot = bots_by_id.get(bot_id)
            if not bot: continue
            
            scores_payload = self._safe_json(r["scores_json"], {})
            reasons_payload = self._safe_json(r["reason_json"], [])
            
            trade_plan = {"entry_plan": [], "stop_loss": {}, "targets": [], "risk": {}}
            tp_row = await self.repository.get_bot_trade_plan(user_id, r["id"])
            if tp_row:
                trade_plan = {
                    "entry_plan": self._safe_json(tp_row["entry_plan"], []),
                    "stop_loss": self._safe_json(tp_row["stop_loss"], {}),
                    "targets": self._safe_json(tp_row["targets"], []),
                    "risk": self._safe_json(tp_row["risk_json"], {})
                }
            elif scores_payload.get("trade_plan"):
                trade_plan = scores_payload.get("trade_plan")

            decisions_by_bot[bot_id] = {
                "id": r["id"],
                "bot_id": bot_id,
                "bot_name": bot["bot_name"],
                "symbol": r["symbol"],
                "setup_name": bot.get("setup_name"),
                "action": r["action"],
                "confidence": r["confidence"],
                "scores_json": scores_payload or daily_scores,
                "requested_amount_eur": scores_payload.get("requested_amount_eur"),
                "amount_eur": scores_payload.get("amount_eur"),
                "guardrails_result": scores_payload.get("guardrails_result"),
                "guardrail_reason": scores_payload.get("guardrail_reason"),
                "metrics": {
                    "position_size": scores_payload.get("position_size"),
                    "exposure_multiplier": scores_payload.get("exposure_multiplier"),
                },
                "reasons": reasons_payload,
                "setup_id": r["setup_id"],
                "strategy_id": r["strategy_id"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
                "setup_match": scores_payload.get("setup_match"),
                "trade_plan": trade_plan,
                "watch_levels": scores_payload.get("watch_levels"),
            }
            
        return {
            "date": str(today),
            "scores": daily_scores,
            "decisions": list(decisions_by_bot.values()),
            "orders": [], "executions": []
        }

    async def get_bot_history(self, user_id: int, days: int) -> List[dict]:
        end_date = date.today()
        start_date = end_date - timedelta(days=max(1, min(days, 365)) - 1)
        
        rows = await self.repository.get_bot_history(user_id, start_date, end_date)
        out = []
        for r in rows:
            scores = self._safe_json(r["scores_json"], {})
            reasons = self._safe_json(r["reason_json"], [])
            
            setup_match = scores.get("setup_match") or {
                "status": "no_snapshot", "summary": "Geen strategie context",
                "detail": "Er is geen actief strategy snapshot beschikbaar.",
                "score": 10, "confidence": "low",
            }
            out.append({
                "decision_id": r["id"],
                "bot_id": r["bot_id"],
                "bot_name": r["bot_name"],
                "symbol": r["symbol"],
                "date": str(r["decision_date"]),
                "decision_ts": r["decision_ts"].isoformat() if r.get("decision_ts") else None,
                "action": r["action"],
                "confidence": r["confidence"],
                "setup_match": setup_match,
                "reasons": reasons if isinstance(reasons, list) else [str(reasons)],
                "status": r["status"]
            })
        return out

    # ==========================
    # MANUL ORDER & SKIP
    # ==========================
    async def create_manual_order(self, payload: BotManualOrderSchema, user_id: int) -> dict:
        notional = round(payload.quantity * payload.price, 2)
        if payload.side == "buy":
            cash_delta = -notional
            qty_delta = payload.quantity
        else:
            cash_delta = notional
            qty_delta = -payload.quantity
            
        order_id = await self.repository.create_manual_order(
            user_id, payload.bot_id, payload.symbol, payload.side, payload.quantity, payload.price
        )
        
        await self.repository.create_bot_execution(user_id, order_id, payload.quantity, payload.price)
        await self.repository.insert_bot_ledger(user_id, payload.bot_id, order_id, payload.symbol, cash_delta, qty_delta, payload.price)
        
        await self.session.commit()
        await asyncio.to_thread(sync_snapshot_all_for_user, user_id)
        
        return {
            "ok": True, "order_id": order_id, "symbol": payload.symbol, "side": payload.side,
            "quantity": payload.quantity, "price": payload.price, "notional_eur": notional, "mode": "manual"
        }

    async def skip_bot_today(self, bot_id: int, report_date_str: Optional[str], user_id: int) -> dict:
        report_date = date.fromisoformat(report_date_str) if report_date_str else date.today()
        decision_id = await self.repository.mark_decision_skipped(user_id, bot_id, report_date)
        if not decision_id:
            raise HTTPException(409, "Decision is al afgehandeld")
            
        await self.repository.cancel_orders_for_decision(user_id, bot_id, decision_id)
        await self.session.commit()
        return {"ok": True, "status": "skipped"}

    # ==========================
    # AGENT TRIGGERS
    # ==========================
    async def run_bot_agent_generate(self, bot_id: int, report_date_str: Optional[str], user_id: int) -> dict:
        report_date = date.fromisoformat(report_date_str) if report_date_str else date.today()
        
        await asyncio.to_thread(sync_run_daily_strategy_snapshot, user_id)
        result = await asyncio.to_thread(sync_run_trading_bot_agent, user_id, report_date, bot_id)
        
        if not result or not getattr(result, "get", lambda k: False)("ok"):
            return {"ok": False}
        return {"ok": True, "bot_id": bot_id, "date": str(report_date)}

    async def mark_bot_executed(self, bot_id: int, decision_id: int, user_id: int) -> dict:
        try:
            await asyncio.to_thread(sync_execute_manual_decision, user_id, bot_id, decision_id)
            await asyncio.to_thread(sync_snapshot_all_for_user, user_id)
            return {"ok": True, "bot_id": bot_id, "decision_id": decision_id, "mode": "manual"}
        except Exception as e:
            raise HTTPException(409, str(e))

    # ==========================
    # BOT PORTFOLIOS
    # ==========================
    async def get_bot_portfolios(self, user_id: int) -> List[dict]:
        bots = await self.repository.get_bot_portfolios_base(user_id)
        if not bots: return []
        
        today = date.today()
        out = []
        for b in bots:
            bot_id = b["id"]
            symbol = "BTC"
            stats_raw = await self.repository.get_bot_ledger_stats(user_id, bot_id, today)
            
            stats = {
                "net_cash_delta_eur": stats_raw["net_cash"],
                "net_executed_cash_delta_eur": stats_raw["executed_cash"],
                "net_qty": stats_raw["net_qty"],
                "today_spent_eur": stats_raw["today_spent"],
                "today_reserved_eur": stats_raw["today_reserved"],
                "today_executed_eur": stats_raw["today_spent"],
                "last_price": None,
                "position_value_eur": None,
                "invested_eur": abs(stats_raw["executed_cash"]),
            }
            
            stats["available_eur"] = max(float(b["budget_total_eur"]) - stats["invested_eur"], 0)
            stats["remaining_daily_eur"] = max(float(b["budget_daily_limit_eur"]) - stats["today_spent_eur"], 0)
            
            # Fetch price individually
            last_price = await self.repository.get_market_price(symbol)
            stats["last_price"] = last_price
            if last_price is not None:
                stats["position_value_eur"] = round(stats["net_qty"] * last_price, 2)
            
            out.append({
                "bot_id": bot_id,
                "name": b["name"],
                "is_active": bool(b["is_active"]),
                "is_live": bool(b["is_live"]),
                "mode": b["mode"],
                "risk_profile": b["risk_profile"],
                "symbol": symbol,
                "budget": {
                    "total_eur": float(b["budget_total_eur"]),
                    "daily_limit_eur": float(b["budget_daily_limit_eur"]),
                    "min_order_eur": float(b["budget_min_order_eur"]),
                    "max_order_eur": float(b["budget_max_order_eur"]),
                },
                "stats": stats
            })
        return out

    async def get_bot_trades(self, bot_id: int, limit: int, user_id: int) -> List[dict]:
        rows = await self.repository.get_bot_trades(user_id, bot_id, max(1, min(100, limit)))
        out = []
        for r in rows:
            out.append({
                "id": r["execution_id"],
                "bot_id": bot_id,
                "symbol": r["symbol"],
                "side": r["side"],
                "qty": float(r["filled_qty"] or 0),
                "price": float(r["avg_fill_price"]) if r["avg_fill_price"] is not None else None,
                "amount_eur": float(r["quote_amount_eur"]) if r["quote_amount_eur"] is not None else None,
                "executed_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "mode": "auto" if r["status"] == "filled" else "manual"
            })
        return out

    # ==========================
    # BOT TRADE PLAN CRUD
    # ==========================
    async def save_trade_plan(self, decision_id: int, payload: TradePlanUpsertSchema, user_id: int) -> dict:
        exists = await self.repository.get_bot_decision(user_id, decision_id)
        if not exists:
            raise HTTPException(404, "Decision niet gevonden")
            
        await self.repository.upsert_bot_trade_plan(
            user_id, decision_id, payload.entry_plan, payload.stop_loss, payload.targets, payload.risk
        )
        await self.session.commit()
        
        return {"ok": True, "decision_id": decision_id, "trade_plan": payload.dict()}

    async def get_trade_plan(self, decision_id: int, user_id: int) -> dict:
        row = await self.repository.get_bot_trade_plan(user_id, decision_id)
        if not row:
            return {"entry_plan": [], "stop_loss": {}, "targets": [], "risk": {}}
        return {
            "entry_plan": self._safe_json(row["entry_plan"], []),
            "stop_loss": self._safe_json(row["stop_loss"], {}),
            "targets": self._safe_json(row["targets"], []),
            "risk": self._safe_json(row["risk_json"], {})
        }

    # ==========================
    # BALANCE HISTORY (PORTFOLIO/BOT)
    # ==========================
    async def get_portfolio_history(self, bucket: str, limit: int, user_id: int) -> List[dict]:
        rows = await self.repository.get_portfolio_balance_history(user_id, bucket, max(1, min(limit, 2000)))
        return [{
            "ts": r["ts"].isoformat() if r.get("ts") else None,
            "equity": float(r["equity_eur"] or 0),
            "cash": float(r["cash_eur"] or 0),
            "btc_qty": float(r["btc_qty"] or 0),
            "btc_value": float(r["btc_value_eur"] or 0),
            "invested": float(r["invested_eur"] or 0),
            "unrealized_pnl": float(r["unrealized_pnl_eur"] or 0)
        } for r in rows]

    async def get_bot_balance_history(self, bot_id: int, bucket: str, limit: int, user_id: int) -> List[dict]:
        rows = await self.repository.get_bot_balance_history(user_id, bot_id, bucket, max(1, min(limit, 2000)))
        out = []
        for r in rows:
            qty = float(r["net_qty"] or 0)
            price = float(r["price_eur"] or 0)
            invested = float(r["invested_eur"] or 0)
            btc_value = qty * price
            out.append({
                "ts": r["ts"].isoformat() if r.get("ts") else None,
                "equity": float(r["equity_eur"] or 0),
                "cash": float(r["cash_eur"] or 0),
                "btc_qty": qty,
                "price": price,
                "invested": invested,
                "btc_value": btc_value,
                "unrealized_pnl": btc_value - invested
            })
        return out
