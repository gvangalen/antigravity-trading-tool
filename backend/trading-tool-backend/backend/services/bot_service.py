import logging
import asyncio
import json
from datetime import date, timedelta, datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.bot_schema import (
    BotConfigCreateSchema,
    BotConfigUpdateSchema,
    BotManualOrderSchema,
    TradePlanUpsertSchema
)
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.engine.guardrails_engine import apply_guardrails
from backend.services.exchange_service import ExchangeService

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
        self.exchange_repo = ExchangeRepository(db_session)

    def _safe_json(self, v, fallback):
        if v is None:
            return fallback
        if isinstance(v, (dict, list)):
            return v
        try:
            return json.loads(v)
        except Exception:
            return fallback

    def _bot_contract(self, bot: Optional[dict]) -> dict:
        if not bot:
            return {
                "bot": None,
                "bot_id": None,
                "strategy_id": None,
                "verified": {"bot": False},
            }

        budget = {
            "total_eur": float(bot.get("budget_total_eur") or 0),
            "daily_limit_eur": float(bot.get("budget_daily_limit_eur") or 0),
            "min_order_eur": float(bot.get("budget_min_order_eur") or 0),
            "max_order_eur": float(bot.get("budget_max_order_eur") or 0),
            "max_asset_exposure_pct": float(bot.get("max_asset_exposure_pct") or 100),
        }
        strategy = None
        if bot.get("strategy_id"):
            strategy = {
                "id": bot.get("strategy_id"),
                "name": bot.get("strategy_name"),
                "setup_type": bot.get("setup_type"),
                "symbol": bot.get("symbol"),
                "timeframe": bot.get("timeframe"),
                "setup": {
                    "id": bot.get("setup_id"),
                    "name": bot.get("setup_name"),
                    "symbol": bot.get("setup_symbol") or bot.get("symbol"),
                    "timeframe": bot.get("timeframe"),
                },
            }
        normalized_bot = {
            "id": bot.get("id"),
            "bot_id": bot.get("id"),
            "name": bot.get("name"),
            "strategy_id": bot.get("strategy_id"),
            "is_active": bool(bot.get("is_active", True)),
            "is_live": bool(bot.get("is_live")),
            "mode": bot.get("mode"),
            "cadence": bot.get("cadence"),
            "risk_profile": bot.get("risk_profile") or "balanced",
            "base_currency": bot.get("base_currency") or "EUR",
            "symbol": bot.get("symbol"),
            "budget": budget,
            "strategy": strategy,
            "created_at": bot["created_at"].isoformat() if bot.get("created_at") else None,
            "updated_at": bot["updated_at"].isoformat() if bot.get("updated_at") else None,
        }
        return {
            "bot": normalized_bot,
            "bot_id": bot.get("id"),
            "strategy_id": bot.get("strategy_id"),
            "mode": bot.get("mode"),
            "is_live": bool(bot.get("is_live")),
            "budget": budget,
            "strategy": strategy,
            "verified": {"bot": True},
        }

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
                "bot_id": r["id"],
                "name": r["name"],
                "is_active": bool(r["is_active"]),
                "is_live": bool(r["is_live"]),
                "mode": r["mode"],
                "cadence": r["cadence"],
                "risk_profile": r["risk_profile"] or "balanced",
                "strategy_id": r.get("strategy_id"),
                "symbol": r.get("symbol"),
                "base_currency": r.get("base_currency") or "EUR",
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

    async def validate_bot_payload(self, raw_payload: dict, user_id: int, is_update: bool = False, bot_id: Optional[int] = None):
        """
        Meticulously validates bot configuration inputs. Prevent bad data
        from entering the database and prevent name conflicts (idempotency/flaky protection).
        """
        # 1. Name unique check
        name = raw_payload.get("name")
        if name:
            if not isinstance(name, str) or not name.strip():
                raise HTTPException(400, "Botnaam is verplicht en mag niet leeg zijn.")
            raw_payload["name"] = name.strip()
            if len(raw_payload["name"]) > 80:
                raise HTTPException(400, "Botnaam mag maximaal 80 karakters bevatten.")

            # Check duplicate name for the user
            duplicate_query = text("""
                SELECT id FROM bot_configs
                WHERE user_id = :user_id AND LOWER(name) = LOWER(:name)
            """)
            res = await self.session.execute(duplicate_query, {"user_id": user_id, "name": name.strip()})
            duplicate = res.fetchone()
            if duplicate:
                # If we're updating, allow same name if it's the current bot itself
                if not is_update or duplicate[0] != bot_id:
                    raise HTTPException(409, f"Een botconfiguratie met de naam '{name}' bestaat al.")

        # 2. Strategy ownership check
        strategy_id = raw_payload.get("strategy_id")
        if strategy_id is not None:
            strategy_query = text("""
                SELECT s.id, COALESCE(st.symbol, raw.data->>'symbol') AS symbol
                FROM strategies s
                LEFT JOIN setups st ON st.id = s.setup_id
                LEFT JOIN LATERAL (SELECT s.data::jsonb AS data) raw ON TRUE
                WHERE s.id = :strategy_id AND s.user_id = :user_id
            """)
            res_strat = await self.session.execute(strategy_query, {"strategy_id": strategy_id, "user_id": user_id})
            strategy_row = res_strat.fetchone()
            if not strategy_row:
                raise HTTPException(400, f"De opgegeven strategy_id ({strategy_id}) bestaat niet of is niet van jou.")
            if not raw_payload.get("symbol") and strategy_row[1]:
                raw_payload["symbol"] = str(strategy_row[1]).upper()

            duplicate_strategy_query = text("""
                SELECT id FROM bot_configs
                WHERE user_id = :user_id AND strategy_id = :strategy_id
                ORDER BY id ASC
                LIMIT 1
            """)
            res_duplicate_strategy = await self.session.execute(
                duplicate_strategy_query,
                {"strategy_id": strategy_id, "user_id": user_id},
            )
            duplicate_strategy = res_duplicate_strategy.fetchone()
            if duplicate_strategy and (not is_update or duplicate_strategy[0] != bot_id):
                raise HTTPException(
                    409,
                    f"Voor strategy_id {strategy_id} bestaat al bot #{duplicate_strategy[0]}. Werk die bot bij in plaats van een tweede bot te maken."
                )

        # 3. Budget checks
        budget_total = raw_payload.get("budget_total_eur", 0.0)
        budget_daily = raw_payload.get("budget_daily_limit_eur", 0.0)
        budget_min = raw_payload.get("budget_min_order_eur", 0.0)
        budget_max = raw_payload.get("budget_max_order_eur", 0.0)

        # Basic non-negative validation
        for label, val in [
            ("budget_total_eur", budget_total),
            ("budget_daily_limit_eur", budget_daily),
            ("budget_min_order_eur", budget_min),
            ("budget_max_order_eur", budget_max)
        ]:
            if val is not None:
                try:
                    num_val = float(val)
                    if num_val < 0:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise HTTPException(400, f"{label} moet een positief getal (of 0) zijn.")

        # Logical budget consistency validations
        budget_total_num = float(budget_total or 0)
        budget_daily_num = float(budget_daily or 0)
        budget_min_num = float(budget_min or 0)
        budget_max_num = float(budget_max or 0)

        if budget_total and budget_daily:
            if budget_daily_num > budget_total_num:
                raise HTTPException(400, "Daglimiet (budget_daily_limit_eur) mag niet groter zijn dan het totaal budget.")

        if budget_min and budget_max:
            if budget_min_num > budget_max_num:
                raise HTTPException(400, "budget_min_order_eur mag niet groter zijn dan budget_max_order_eur.")

        if budget_max and budget_total:
            if budget_max_num > budget_total_num:
                raise HTTPException(400, "budget_max_order_eur mag niet groter zijn dan het totaal budget.")

        is_live = bool(raw_payload.get("is_live"))
        mode_value = str(raw_payload.get("mode") or "manual").lower()
        is_active = bool(raw_payload.get("is_active", True))
        requires_budget = is_live or (is_active and mode_value in {"semi-auto", "auto"})
        if requires_budget:
            missing = [
                label for label, value in [
                    ("budget_total_eur", budget_total_num),
                    ("budget_daily_limit_eur", budget_daily_num),
                    ("budget_min_order_eur", budget_min_num),
                    ("budget_max_order_eur", budget_max_num),
                ]
                if value <= 0
            ]
            if missing:
                raise HTTPException(
                    400,
                    f"Live of automatische bots vereisen expliciete budgetlimieten: {', '.join(missing)}."
                )

        if is_live:
            keys = await self.exchange_repo.get_active_keys(user_id)
            if not keys:
                raise HTTPException(400, "Live bot vereist actieve exchange keys voordat hij kan worden opgeslagen.")

        # 4. Exposure check
        exposure = raw_payload.get("max_asset_exposure_pct")
        if exposure is not None:
            try:
                num_exp = float(exposure)
                if num_exp < 0.0 or num_exp > 100.0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise HTTPException(400, "max_asset_exposure_pct moet een getal tussen 0.0 en 100.0 zijn.")

        # 5. List options validation
        cadence = raw_payload.get("cadence")
        if cadence is not None:
            cadence_value = str(cadence).lower()
            if cadence_value not in ["hourly", "daily", "weekly", "monthly"]:
                raise HTTPException(400, "cadence moet één van 'hourly', 'daily', 'weekly', of 'monthly' zijn.")
            raw_payload["cadence"] = cadence_value

        mode = raw_payload.get("mode")
        if mode is not None:
            mode_value = str(mode).lower()
            if mode_value == "semi":
                raw_payload["mode"] = "semi-auto"
                mode_value = "semi-auto"
            if mode_value not in ["manual", "semi-auto", "auto"]:
                raise HTTPException(400, "mode moet één van 'manual', 'semi-auto', of 'auto' zijn.")
            raw_payload["mode"] = mode_value

        risk = raw_payload.get("risk_profile")
        if risk is not None:
            risk_value = str(risk).lower()
            if risk_value not in ["conservative", "balanced", "aggressive"]:
                raise HTTPException(400, "risk_profile moet één van 'conservative', 'balanced', of 'aggressive' zijn.")
            raw_payload["risk_profile"] = risk_value

        base_currency = raw_payload.get("base_currency")
        if base_currency is not None:
            currency_value = str(base_currency).upper()
            if currency_value not in {"EUR", "USD"}:
                raise HTTPException(400, "base_currency moet EUR of USD zijn.")
            raw_payload["base_currency"] = currency_value

    async def create_bot_config(self, payload: BotConfigCreateSchema, user_id: int) -> dict:
        data = payload.dict()
        data["user_id"] = user_id
        data.setdefault("is_live", False)
        data.setdefault("symbol", None)

        # Meticulously validate payload
        await self.validate_bot_payload(data, user_id, is_update=False)

        bot_id = await self.repository.create_bot_config(data)
        await self.session.commit()
        bot = await self.repository.get_bot_config(user_id, bot_id)
        return {"ok": True, "id": bot_id, **self._bot_contract(bot)}

    async def update_bot_config(self, bot_id: int, payload: BotConfigUpdateSchema, user_id: int) -> dict:
        existing = await self.repository.get_bot_config(user_id, bot_id)
        if not existing:
            raise HTTPException(404, "Bot niet gevonden")

        updates = payload.dict(exclude_unset=True)
        # Handle aliases
        if "total_eur" in updates: updates["budget_total_eur"] = updates.pop("total_eur")
        if "daily_limit_eur" in updates: updates["budget_daily_limit_eur"] = updates.pop("daily_limit_eur")
        if "min_order_eur" in updates: updates["budget_min_order_eur"] = updates.pop("min_order_eur")
        if "max_order_eur" in updates: updates["budget_max_order_eur"] = updates.pop("max_order_eur")

        # Merge updates on top of existing config for cross-field consistency validations
        merged = dict(existing)
        for k, v in updates.items():
            merged[k] = v

        await self.validate_bot_payload(merged, user_id, is_update=True, bot_id=bot_id)

        updated_id = await self.repository.update_bot_config(user_id, bot_id, updates)
        if not updated_id:
            raise HTTPException(404, "Bot niet gevonden")
            
        await self.session.commit()
        bot = await self.repository.get_bot_config(user_id, bot_id)
        return {"ok": True, **self._bot_contract(bot)}

    async def delete_bot_config(self, bot_id: int, user_id: int) -> dict:
        deleted = await self.repository.delete_bot_config(user_id, bot_id)
        if not deleted:
            raise HTTPException(404, "Bot niet gevonden")
        await self.session.commit()
        return {"ok": True, "bot_id": bot_id, "deleted": True}

    # ==========================
    # BOT DECISIONS (TODAY/HISTORY)
    # ==========================
    async def get_bot_today(self, user_id: int, symbol: str = "BTC") -> dict:
        today = date.today()
        daily_scores = await self.repository.get_daily_scores_row(user_id, today) or {
            "macro": 10, "technical": 10, "market": 10, "setup": 10
        }
        
        # 🔥 SYNC: Probeer master insight op te halen voor consistente scores met Overview
        from backend.infrastructure.repositories.score_repository import ScoreRepository
        score_repo = ScoreRepository(self.session)
        master = await score_repo.get_master_score(user_id, symbol=symbol)
        
        if master and master.top_signals:
            meta = master.top_signals
            if isinstance(meta, str):
                try: meta = json.loads(meta)
                except: meta = {}
            
            domains = meta.get("domains", {})
            if domains:
                # Overschrijf raw scores met de AI-geïnterpreteerde domein scores
                if "macro" in domains: daily_scores["macro"] = domains["macro"].get("score", daily_scores["macro"])
                if "technical" in domains: daily_scores["technical"] = domains["technical"].get("score", daily_scores["technical"])
                if "market" in domains: daily_scores["market"] = domains["market"].get("score", daily_scores["market"])
                if "setup" in domains: daily_scores["setup"] = domains["setup"].get("score", daily_scores["setup"])
        
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
    async def preview_manual_order(self, payload: BotManualOrderSchema, user_id: int):
        """
        Provides a real-time preview of a manual order with fees and guardrails.
        This endpoint never executes or persists an order.
        """
        bot = await self.repository.get_bot_config(user_id, payload.bot_id)
        if not bot:
            raise HTTPException(404, "Bot niet gevonden.")

        self._validate_manual_order_payload(payload)

        # Default values from payload
        price = payload.price
        amount_eur = payload.value_eur or (payload.quantity * payload.price)
        fee_rate = 0.0025 # Default Bitvavo taker fee
        fee_eur = amount_eur * fee_rate
        stats = await self.repository.get_bot_ledger_stats(user_id, payload.bot_id, date.today())

        if not price or price <= 0:
            market_price = await self.repository.get_market_price(payload.symbol)
            if market_price:
                price = market_price
            else:
                raise HTTPException(400, "Geen geldige prijs beschikbaar voor order preview.")

        if bot.get("is_live"):
            keys = await self.exchange_repo.get_active_keys(user_id)
            if keys:
                key = keys[0]
                try:
                    client = await ExchangeService.get_client(
                        key.exchange_name, key.api_key, key.api_secret, key.api_passphrase
                    )
                    ticker = await ExchangeService.fetch_ticker(client, payload.symbol)
                    if ticker and 'last' in ticker:
                        price = float(ticker['last'])
                    
                    # Re-instantiate for fees
                    client = await ExchangeService.get_client(
                        key.exchange_name, key.api_key, key.api_secret, key.api_passphrase
                    )
                    fees = await ExchangeService.fetch_trading_fees(client, payload.symbol)
                    if fees and 'taker' in fees:
                        fee_rate = float(fees['taker'])
                except Exception as e:
                    logger.warning(f"⚠️ Could not fetch live preview data: {e}")

        # Recalculate based on best available data
        fee_eur = amount_eur * fee_rate
        quantity = (amount_eur - fee_eur) / price if payload.side == "buy" else (amount_eur / price)
        
        # If selling, fee is usually deducted from the received EUR
        if payload.side == "sell":
             quantity = payload.quantity
             gross_eur = quantity * price
             fee_eur = gross_eur * fee_rate
             net_eur = gross_eur - fee_eur
        else:
             # Buying: We spend amount_eur total (Gross)
             gross_eur = amount_eur
             net_eur = amount_eur - fee_eur

        invested = abs(float(stats.get("executed_cash", 0) or 0))
        today_allocated = float(stats.get("today_spent", 0) or 0) + float(stats.get("today_reserved", 0) or 0)
        current_asset_value = max(float(stats.get("net_qty", 0) or 0), 0.0) * price
        total_budget = float(bot.get("budget_total_eur", 0) or 0)
        cash_balance = max(total_budget - invested, 0.0) if total_budget > 0 else max(amount_eur, 0.0)
        portfolio_value = max(total_budget, current_asset_value, invested, amount_eur)
        guardrails = apply_guardrails(
            proposed_amount_eur=gross_eur if payload.side == "buy" else 0.0,
            portfolio_value_eur=portfolio_value,
            current_asset_value_eur=current_asset_value,
            invested_eur=invested,
            today_allocated_eur=today_allocated,
            cash_balance_eur=cash_balance,
            kill_switch=bool(bot.get("is_active", True)),
            max_trade_risk_eur=bot.get("budget_max_order_eur"),
            daily_allocation_eur=bot.get("budget_daily_limit_eur"),
            max_asset_exposure_pct=bot.get("max_asset_exposure_pct"),
            total_budget_eur=bot.get("budget_total_eur"),
            min_order_eur=bot.get("budget_min_order_eur"),
        )

        if payload.side == "sell":
            current_qty = max(float(stats.get("net_qty", 0) or 0), 0.0)
            sell_allowed = payload.quantity > 0 and payload.quantity <= current_qty
            guardrails = {
                "allowed": sell_allowed,
                "adjusted_amount_eur": round(gross_eur if sell_allowed else 0.0, 2),
                "original_amount_eur": round(gross_eur, 2),
                "warnings": [] if sell_allowed else ["insufficient_position"],
                "blocked_by": None if sell_allowed else "insufficient_position",
                "reason": None if sell_allowed else "Niet genoeg positie om dit aantal te verkopen",
                "debug_code": None if sell_allowed else "insufficient_position",
                "guardrails": {
                    "current_qty": round(current_qty, 8),
                    "requested_qty": round(payload.quantity, 8),
                },
            }

        draft = {
            "type": "manual_order_preview",
            "bot_id": payload.bot_id,
            "bot_name": bot.get("name"),
            "symbol": payload.symbol,
            "side": payload.side,
            "paper_or_live": "live" if bot.get("is_live", False) else "paper",
            "requires_explicit_confirmation": True,
            "not_persisted": True,
        }

        return {
            "symbol": payload.symbol,
            "side": payload.side,
            "price": price,
            "gross_eur": round(gross_eur, 2),
            "fee_eur": round(fee_eur, 2),
            "fee_rate": fee_rate,
            "net_eur": round(net_eur, 2),
            "quantity": round(quantity, 8),
            "is_live": bot.get("is_live", False),
            "guardrails": guardrails,
            "draft": draft,
        }

    async def create_manual_order(self, payload: BotManualOrderSchema, user_id: int) -> dict:
        self._validate_manual_order_payload(payload)

        # 1. Fetch bot config to get limits
        bot = await self.repository.get_bot_config(user_id, payload.bot_id)
        if not bot:
            raise HTTPException(404, "Bot niet gevonden")
            
        # 2. Fetch current stats
        stats = await self.repository.get_bot_ledger_stats(user_id, payload.bot_id, date.today())
        
        # 3. Guardrail check for BUY and SELL orders
        notional = round(payload.quantity * payload.price, 2)
        if notional <= 0:
            raise HTTPException(400, "Orderwaarde moet groter zijn dan 0.")

        min_order = float(bot.get("budget_min_order_eur", 0) or 0)
        if min_order > 0 and notional < (min_order - 0.01):
            raise HTTPException(400, f"Minimale ordergrootte niet gehaald (Min {min_order} EUR)")
        
        if payload.side == "buy":
            # Total Budget Check
            invested = abs(float(stats.get("executed_cash", 0)))
            total_budget = float(bot.get("budget_total_eur", 0))
            if total_budget > 0 and (invested + notional) > (total_budget + 0.01):
                raise HTTPException(400, f"Totaal budget overschreden (Max {total_budget} EUR)")
                
            # Daily Limit Check
            daily_limit = float(bot.get("budget_daily_limit_eur", 0))
            today_spent = float(stats.get("today_spent", 0))
            if daily_limit > 0 and (today_spent + notional) > (daily_limit + 0.01):
                raise HTTPException(400, f"Daglimiet overschreden (Max {daily_limit} EUR, vandaag al {today_spent} EUR besteed)")
                
            # Max Order Check
            max_order = float(bot.get("budget_max_order_eur", 0))
            if max_order > 0 and notional > (max_order + 0.01):
                raise HTTPException(400, f"Maximale ordergrootte overschreden (Max {max_order} EUR)")

            guardrails = apply_guardrails(
                proposed_amount_eur=notional,
                portfolio_value_eur=max(total_budget, invested, notional),
                current_asset_value_eur=max(float(stats.get("net_qty", 0) or 0), 0.0) * payload.price,
                invested_eur=invested,
                today_allocated_eur=today_spent,
                cash_balance_eur=max(total_budget - invested, 0.0) if total_budget > 0 else notional,
                kill_switch=bool(bot.get("is_active", True)),
                max_trade_risk_eur=bot.get("budget_max_order_eur"),
                daily_allocation_eur=bot.get("budget_daily_limit_eur"),
                max_asset_exposure_pct=bot.get("max_asset_exposure_pct"),
                total_budget_eur=bot.get("budget_total_eur"),
                min_order_eur=bot.get("budget_min_order_eur"),
            )
            if not guardrails.get("allowed", False):
                raise HTTPException(400, guardrails.get("reason") or "Order geblokkeerd door bot guardrails.")
        else:
            current_qty = max(float(stats.get("net_qty", 0) or 0), 0.0)
            if payload.quantity > (current_qty + 1e-12):
                raise HTTPException(
                    400,
                    f"Niet genoeg positie om te verkopen. Beschikbaar: {round(current_qty, 8)} {payload.symbol}."
                )

        order_id, is_new_order = await self.repository.create_manual_order(
            user_id,
            payload.bot_id,
            payload.symbol,
            payload.side,
            payload.quantity,
            payload.price,
            idempotency_key=payload.idempotency_key,
            quote_amount_eur=notional,
            status="pending" if bot.get("is_live") else "filled",
        )
        if not is_new_order:
            existing = await self.repository.get_manual_order_by_idempotency_key(user_id, payload.idempotency_key)
            return {
                "ok": True,
                "duplicate": True,
                "order_id": order_id,
                "symbol": existing.get("symbol") if existing else payload.symbol,
                "side": existing.get("side") if existing else payload.side,
                "quantity": float(existing.get("quantity")) if existing and existing.get("quantity") is not None else payload.quantity,
                "price": float(existing.get("limit_price")) if existing and existing.get("limit_price") is not None else payload.price,
                "notional_eur": float(existing.get("quote_amount_eur")) if existing and existing.get("quote_amount_eur") is not None else notional,
                "mode": "manual",
            }

        if payload.side == "buy":
            cash_delta = -notional
            qty_delta = payload.quantity
        else:
            cash_delta = notional
            qty_delta = -payload.quantity
            
        # 4. Handle Live Exchange Execution
        if bot.get("is_live"):
            try:
                keys = await self.exchange_repo.get_active_keys(user_id)
                if not keys:
                    raise HTTPException(400, "Geen actieve exchange keys gevonden voor live trading.")
                
                # Use the first active key (assuming Bitvavo for now based on user context)
                key = keys[0]
                client = await ExchangeService.get_client(
                    key.exchange_name, key.api_key, key.api_secret, key.api_passphrase
                )
                
                # Execute on exchange
                logger.info(f"⚡ LIVE ORDER: Sending {payload.side} {payload.quantity} {payload.symbol} to {key.exchange_name}")
                
                # Fetch latest price to ensure quantity is correct if value_eur is used
                final_qty = payload.quantity
                final_price = payload.price
                
                if payload.value_eur and payload.value_eur > 0:
                    ticker = await ExchangeService.fetch_ticker(client, payload.symbol)
                    if ticker and 'last' in ticker:
                        live_ex_price = float(ticker['last'])
                        # Recalculate quantity based on REAL exchange price
                        final_qty = payload.value_eur / live_ex_price
                        final_price = live_ex_price
                        logger.info(f"🔄 Recalculated live qty: {final_qty} @ {final_price} (Target: {payload.value_eur} EUR)")
                    
                    # Re-instantiate client because fetch_ticker closes it
                    client = await ExchangeService.get_client(
                        key.exchange_name, key.api_key, key.api_secret, key.api_passphrase
                    )

                await ExchangeService.create_order(
                    client, payload.symbol, payload.side, final_qty, final_price, 
                    order_type='limit'
                )
                
                # Update payload values for internal ledger consistency
                payload.quantity = final_qty
                payload.price = final_price
            except HTTPException:
                await self.repository.update_manual_order_status(user_id, order_id, "failed")
                await self.session.commit()
                raise
            except Exception as e:
                await self.repository.update_manual_order_status(user_id, order_id, "failed")
                await self.session.commit()
                logger.error(f"❌ Exchange Order Failed: {str(e)}")
                raise HTTPException(500, f"Order bij exchange mislukt: {str(e)}")

        if bot.get("is_live"):
            notional = round(payload.quantity * payload.price, 2)
            if payload.side == "buy":
                cash_delta = -notional
                qty_delta = payload.quantity
            else:
                cash_delta = notional
                qty_delta = -payload.quantity
            await self.repository.update_manual_order_status(user_id, order_id, "filled")

        await self.repository.create_bot_execution(user_id, order_id, payload.quantity, payload.price)
        await self.repository.insert_bot_ledger(user_id, payload.bot_id, order_id, payload.symbol, cash_delta, qty_delta, payload.price)
        
        await self.session.commit()
        await asyncio.to_thread(sync_snapshot_all_for_user, user_id)
        
        return {
            "ok": True, "order_id": order_id, "symbol": payload.symbol, "side": payload.side,
            "quantity": payload.quantity,
            "price": payload.price,
            "notional_eur": notional,
            "mode": "manual",
            "duplicate": False,
        }

    def _validate_manual_order_payload(self, payload: BotManualOrderSchema) -> None:
        side = str(payload.side or "").lower().strip()
        if side not in {"buy", "sell"}:
            raise HTTPException(400, "side moet 'buy' of 'sell' zijn.")
        payload.side = side

        symbol = str(payload.symbol or "").strip().upper()
        if len(symbol) < 2 or len(symbol) > 20:
            raise HTTPException(400, "symbol is verplicht en moet 2-20 karakters lang zijn.")
        payload.symbol = symbol

        if payload.quantity is None or float(payload.quantity) <= 0:
            raise HTTPException(400, "quantity moet groter zijn dan 0.")
        if payload.price is None or float(payload.price) <= 0:
            raise HTTPException(400, "price moet groter zijn dan 0.")
        if payload.value_eur is not None and float(payload.value_eur) <= 0:
            raise HTTPException(400, "value_eur moet groter zijn dan 0 wanneer meegegeven.")
        if payload.idempotency_key is not None:
            key = str(payload.idempotency_key).strip()
            if len(key) < 8 or len(key) > 120:
                raise HTTPException(400, "idempotency_key moet tussen 8 en 120 karakters lang zijn.")
            payload.idempotency_key = key

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
    async def get_portfolio_history(self, bucket: str, limit: int, user_id: int, is_live: Optional[bool] = None) -> List[dict]:
        if is_live is not None:
            rows = await self.repository.get_filtered_portfolio_balance_history(user_id, is_live, bucket, max(1, min(limit, 2000)))
            return [{
                "ts": r["ts"].isoformat() if r.get("ts") else None,
                "equity": float(r["equity_eur"] or 0),
                "cash": float(r["cash_eur"] or 0),
                "btc_qty": float(r["btc_qty"] or 0),
                "btc_value": float(r["btc_qty"] * r["price_eur"]) if r.get("btc_qty") and r.get("price_eur") else 0,
                "invested": float(r["invested_eur"] or 0),
                "unrealized_pnl": float((r["btc_qty"] * r["price_eur"]) - r["invested_eur"]) if r.get("btc_qty") and r.get("price_eur") else 0
            } for r in rows]

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
