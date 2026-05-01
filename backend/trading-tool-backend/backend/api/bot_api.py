import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Request

from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.services.bot_service import BotService
from backend.schemas.bot_schema import (
    BotConfigCreateSchema,
    BotConfigUpdateSchema,
    BotManualOrderSchema,
    TradePlanUpsertSchema,
    BotGenerateTodaySchema,
    BotSkipSchema,
    BotMarkExecutedSchema
)

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_bot_service(db: AsyncSession = Depends(get_db)):
    return BotService(db)

# ==========================================================
# 📦 BOT CONFIGS
# ==========================================================
@router.get("/bot/configs")
async def get_bot_configs(
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_configs(current_user["id"])

@router.post("/bot/configs")
async def create_bot_config(
    payload: BotConfigCreateSchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.create_bot_config(payload, current_user["id"])

@router.put("/bot/configs/{bot_id}")
async def update_bot_config(
    bot_id: int,
    payload: BotConfigUpdateSchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.update_bot_config(bot_id, payload, current_user["id"])

@router.delete("/bot/configs/{bot_id}")
async def delete_bot_config(
    bot_id: int,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.delete_bot_config(bot_id, current_user["id"])

# ==========================================================
# 📄 BOT DECISIONS (TODAY/HISTORY)
# ==========================================================
@router.get("/bot/today")
async def get_bot_today(
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_today(current_user["id"])

@router.get("/bot/history")
async def get_bot_history(
    days: int = 30,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_history(current_user["id"], days)

# ==========================================================
# 🔁 AI AGENT TRIGGERS & SKIPS
# ==========================================================
@router.post("/bot/generate/today")
async def generate_bot_today(
    payload: BotGenerateTodaySchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.run_bot_agent_generate(payload.bot_id, payload.report_date, current_user["id"])

@router.post("/bot/skip")
async def skip_bot_today(
    payload: BotSkipSchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.skip_bot_today(payload.bot_id, payload.report_date, current_user["id"])

@router.post("/bot/mark_executed")
async def mark_bot_executed(
    payload: BotMarkExecutedSchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.mark_bot_executed(payload.bot_id, payload.decision_id, current_user["id"])

# ==========================================================
# 🟡 MANUAL ORDERS (PAPER TRADE / DISCRETIONARY)
# ==========================================================
@router.post("/orders/manual")
async def create_manual_order(
    payload: BotManualOrderSchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.create_manual_order(payload, current_user["id"])

# ==========================================================
# 📦 BOT PORTFOLIOS
# ==========================================================
@router.get("/bot/portfolios")
async def get_bot_portfolios(
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_portfolios(current_user["id"])

# ==========================================================
# 📊 BOT TRADES
# ==========================================================
@router.get("/bot/trades")
async def get_bot_trades(
    bot_id: int,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_trades(bot_id, limit, current_user["id"])

# ==========================================================
# 💾 BOT TRADE PLAN (UPSERT & GET)
# ==========================================================
@router.post("/bot/trade-plan/{decision_id}")
async def save_trade_plan(
    decision_id: int,
    payload: TradePlanUpsertSchema,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.save_trade_plan(decision_id, payload, current_user["id"])

@router.get("/bot/trade-plan/{decision_id}")
async def get_trade_plan(
    decision_id: int,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_trade_plan(decision_id, current_user["id"])

# ==========================================================
# 📈 BALANCE HISTORY (PRO)
# ==========================================================
@router.get("/portfolio/balance-history")
async def get_portfolio_balance_history(
    bucket: str = "1h",
    limit: int = 500,
    is_live: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_portfolio_history(bucket, limit, current_user["id"], is_live)

@router.get("/bot/balance-history")
async def get_bot_balance_history(
    bot_id: int,
    bucket: str = "1h",
    limit: int = 500,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_balance_history(bot_id, bucket, limit, current_user["id"])
