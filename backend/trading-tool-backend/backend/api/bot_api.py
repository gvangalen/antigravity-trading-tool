import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, condecimal, conlist
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.utils.rate_limit import InMemoryRateLimiter, client_ip
from backend.services.bot_service import BotService
from backend.services.finn_trade_review_service import FinnTradeReviewService
from backend.services.finn_trade_screenshot import MAX_BYTES
from backend.services.finn_trade_analysis_service import FinnTradeAnalysisService
from backend.services.finn_trade_review_rollout import trade_review_enabled, require_trade_review_access
from backend.services.finn_exchange_import_service import FinnExchangeImportService
from backend.services.finn_exchange_trade_review_service import FinnExchangeTradeReviewService
from backend.schemas.finn_exchange_trade_review_schema import ExchangeTradeReviewCreate
from backend.services.finn_bybit_derivative_import_service import FinnBybitDerivativeImportService
from backend.services.finn_bybit_derivative_review_service import FinnBybitDerivativeReviewService
from backend.schemas.finn_bybit_derivative_schema import BybitDerivativeReviewCreate
from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter
from backend.services.live_portfolio_allocation_service import read_live_account, replace_allocations
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
order_rate_limiter = InMemoryRateLimiter(requests_limit=20, window_seconds=60)
review_rate_limiter = InMemoryRateLimiter(requests_limit=30, window_seconds=60)
allocation_rate_limiter = InMemoryRateLimiter(requests_limit=3, window_seconds=60)
ORDER_USER_LIMIT = 20
ORDER_IP_LIMIT = 30
LOCAL_PROXY_IPS = {"127.0.0.1", "::1", "localhost"}


class FinnTradeReviewNote(BaseModel):
    note: str = Field(max_length=2000)


class FinnTradeQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


def _apply_sensitive_order_rate_limit(*, user_id: int, request: Request, action_key: str) -> None:
    ip_addr = client_ip(request)
    order_rate_limiter.check_rate_limit(
        f"user_{user_id}:{action_key}",
        limit=ORDER_USER_LIMIT,
        detail="Te veel gevoelige orderverzoeken. Wacht kort en probeer opnieuw.",
    )
    if ip_addr not in LOCAL_PROXY_IPS:
        order_rate_limiter.check_rate_limit(
            f"ip_{ip_addr}:{action_key}",
            limit=ORDER_IP_LIMIT,
            detail="Te veel gevoelige orderverzoeken vanaf dit IP-adres. Wacht kort en probeer opnieuw.",
        )

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
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_today(current_user["id"], symbol=symbol)

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
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.run_bot_agent_generate(
        payload.bot_id,
        payload.report_date,
        current_user["id"],
        trace_id=getattr(request.state, "trace_id", None),
    )

@router.post("/bot/paper/reassess")
async def reassess_paper_bot(
    payload: BotGenerateTodaySchema,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service),
):
    return await service.run_bot_agent_generate(
        payload.bot_id,
        payload.report_date,
        current_user["id"],
        trace_id=getattr(request.state, "trace_id", None),
        paper_only=True,
    )

@router.post("/bot/skip")
async def skip_bot_today(
    payload: BotSkipSchema,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    result = await service.skip_bot_today(payload.bot_id, payload.report_date, current_user["id"])
    result["trace_id"] = getattr(request.state, "trace_id", None)
    return result

@router.post("/bot/mark_executed")
async def mark_bot_executed(
    payload: BotMarkExecutedSchema,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    result = await service.mark_bot_executed(payload.bot_id, payload.decision_id, current_user["id"])
    result["trace_id"] = getattr(request.state, "trace_id", None)
    return result

# ==========================================================
# 🟡 MANUAL ORDERS (PAPER TRADE / DISCRETIONARY)
# ==========================================================
@router.get("/bot/{bot_id}/paper-price-eur")
async def get_paper_price_eur(
    bot_id: int,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service),
):
    return await service.get_paper_price_eur(current_user["id"], bot_id)

@router.post("/orders/preview")
async def preview_manual_order(
    payload: BotManualOrderSchema,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = BotService(db)
        return await service.preview_manual_order(payload, current_user["id"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [preview_manual_order] Error: {e}", exc_info=True)
        raise HTTPException(500, detail="Preview van order mislukt.")

@router.post("/orders/manual")
async def create_manual_order(
    payload: BotManualOrderSchema,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    trace_id = getattr(request.state, "trace_id", None)
    _apply_sensitive_order_rate_limit(user_id=current_user["id"], request=request, action_key="manual_order")
    try:
        return await service.create_manual_order(payload, current_user["id"], trace_id=trace_id)
    except HTTPException as exc:
        await service.record_live_order_block_from_exception(
            payload,
            current_user["id"],
            exc,
            source="manual_order_execute",
            trace_id=trace_id,
        )
        raise

@router.post("/orders/manual/preflight")
async def preflight_manual_order(
    payload: BotManualOrderSchema,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    trace_id = getattr(request.state, "trace_id", None)
    _apply_sensitive_order_rate_limit(user_id=current_user["id"], request=request, action_key="manual_order_preflight")
    try:
        return await service.preflight_manual_order(payload, current_user["id"], trace_id=trace_id)
    except HTTPException as exc:
        await service.record_live_order_block_from_exception(
            payload,
            current_user["id"],
            exc,
            source="manual_order_preflight",
            trace_id=trace_id,
        )
        raise

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
@router.get("/bot/trades/all")
async def get_account_bot_trades(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service),
):
    return await service.get_account_bot_trades(current_user["id"], limit, offset)

@router.get("/bot/trades")
async def get_bot_trades(
    bot_id: int,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_trades(bot_id, limit, current_user["id"])

@router.get("/bot/exchange-trade-imports")
async def list_finn_exchange_imports(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    return {"sources": await FinnExchangeImportService(db).status(current_user["id"])}


@router.post("/bot/exchange-trade-imports/{exchange_name}/sync")
async def sync_finn_exchange_import(
    exchange_name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"exchange_import_sync:{current_user['id']}", limit=3)
    try:
        return await FinnExchangeImportService(db).sync(current_user["id"], exchange_name)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Exchange-import is tijdelijk niet beschikbaar") from None


@router.get("/bot/exchange-trade-imports/{source_id}/fills")
async def list_finn_exchange_import_fills(
    source_id: int,
    limit: int = 50,
    offset: int = 0,
    before_at: datetime | None = None,
    before_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"exchange_import_fills:{current_user['id']}", limit=30)
    return await FinnExchangeImportService(db).fills(current_user["id"], source_id,
                                                     limit=limit, offset=offset,
                                                     before_at=before_at, before_id=before_id)


@router.post("/bot/exchange-trade-reviews", status_code=201)
async def create_finn_exchange_trade_review(
    payload: ExchangeTradeReviewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"exchange_review_create:{current_user['id']}", limit=5)
    return await FinnExchangeTradeReviewService(db).create(
        current_user["id"], fill_ids=payload.fill_ids,
        closure_confirmed=payload.closure_confirmed,
        same_account_confirmed=payload.same_account_confirmed,
        idempotency_key=payload.idempotency_key,
    )


@router.get("/bot/bybit-derivatives")
async def list_bybit_derivative_imports(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    return {"sources": await FinnBybitDerivativeImportService(db).status(current_user["id"])}


@router.post("/bot/bybit-derivatives/sync")
async def sync_bybit_derivatives(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"bybit_derivative_sync:{current_user['id']}", limit=3)
    return await FinnBybitDerivativeImportService(db).sync(current_user["id"])


@router.get("/bot/bybit-derivatives/{source_id}/{category}/executions")
async def list_bybit_derivative_executions(
    source_id: int, category: str, limit: int = 50, offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"bybit_derivative_evidence:{current_user['id']}", limit=30)
    return await FinnBybitDerivativeImportService(db).executions(
        current_user["id"], source_id, category, limit=limit, offset=offset)


@router.get("/bot/bybit-derivatives/{source_id}/{category}/streams")
async def list_bybit_derivative_streams(
    source_id: int, category: str, limit: int = 50, offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"bybit_derivative_streams:{current_user['id']}", limit=30)
    return await FinnBybitDerivativeImportService(db).streams(
        current_user["id"], source_id, category, limit=limit, offset=offset)


@router.get("/bot/bybit-derivatives/{source_id}/{category}/episodes")
async def list_bybit_derivative_episodes(
    source_id: int, category: str, symbol: str | None = None,
    position_idx: int | None = None, limit: int = 50, offset: int = 0,
    before_at: datetime | None = None, before_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"bybit_derivative_episodes:{current_user['id']}", limit=20)
    return await FinnBybitDerivativeReviewService(db).candidates(
        current_user["id"], source_id, category, symbol=symbol,
        position_idx=position_idx, limit=limit, offset=offset,
        before_at=before_at, before_id=before_id)


@router.post("/bot/bybit-derivative-reviews", status_code=201)
async def create_bybit_derivative_review(
    payload: BybitDerivativeReviewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"bybit_derivative_create:{current_user['id']}", limit=5)
    return await FinnBybitDerivativeReviewService(db).create(
        current_user["id"], source_id=payload.source_id, category=payload.category,
        symbol=payload.symbol.upper(), position_idx=payload.position_idx,
        episode_key=payload.episode_key, closure_confirmed=payload.closure_confirmed,
        idempotency_key=payload.idempotency_key,
        before_at=payload.before_at, before_id=payload.before_id)


@router.get("/bot/trade-reviews")
async def list_finn_trade_reviews(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (1 <= limit <= 100) or offset < 0:
        raise HTTPException(422, "Ongeldige paginering")
    review_rate_limiter.check_rate_limit(f"trade_review_list:{current_user['id']}", limit=30)
    if not trade_review_enabled(current_user["id"]):
        return {"status": "disabled", "items": [], "total": 0,
                "weekly": {"trades": 0, "analyzed": 0, "pending": 0, "unavailable": 0,
                           "patterns": []}, "excluded": {}}
    return await FinnTradeReviewService(db).list_reviews(current_user["id"], limit, offset)


@router.get("/bot/trade-reviews/{review_id}")
async def get_finn_trade_review(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    return await FinnTradeReviewService(db).get_review(current_user["id"], review_id)


@router.put("/bot/trade-reviews/{review_id}/note")
async def save_finn_trade_review_note(
    review_id: int,
    payload: FinnTradeReviewNote,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    return await FinnTradeReviewService(db).update_note(current_user["id"], review_id, payload.note)


@router.put("/bot/trade-reviews/{review_id}/screenshot")
async def put_finn_trade_review_screenshot(
    review_id: int, request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"trade_review_upload:{current_user['id']}", limit=10)
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/png":
        raise HTTPException(415, "Alleen PNG wordt ondersteund")
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_BYTES:
            raise HTTPException(413, "Screenshot is groter dan 3 MB")
    return await FinnTradeReviewService(db).save_screenshot(current_user["id"], review_id, bytes(chunks))


@router.get("/bot/trade-reviews/{review_id}/screenshot")
async def get_finn_trade_review_screenshot(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    data = await FinnTradeReviewService(db).get_screenshot(current_user["id"], review_id)
    return Response(data, media_type="image/png", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.delete("/bot/trade-reviews/{review_id}/screenshot", status_code=204)
async def delete_finn_trade_review_screenshot(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    await FinnTradeReviewService(db).delete_screenshot(current_user["id"], review_id)
    return Response(status_code=204)


@router.get("/bot/trade-reviews/{review_id}/chart")
async def get_finn_trade_review_chart(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"trade_review_chart:{current_user['id']}", limit=20)
    return await FinnTradeReviewService(db).get_chart(current_user["id"], review_id)


@router.post("/bot/trade-reviews/{review_id}/analyze")
async def analyze_finn_trade_review(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"trade_review_ai:{current_user['id']}", limit=6)
    return await FinnTradeAnalysisService(db).analyze(current_user["id"], review_id, retry=True)


@router.get("/bot/trade-reviews/{review_id}/messages")
async def get_finn_trade_review_messages(
    review_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    return await FinnTradeAnalysisService(db).messages(current_user["id"], review_id)


@router.post("/bot/trade-reviews/{review_id}/messages")
async def ask_finn_trade_review(
    review_id: int, payload: FinnTradeQuestion,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_trade_review_access(current_user["id"])
    review_rate_limiter.check_rate_limit(f"trade_review_ai:{current_user['id']}", limit=6)
    return await FinnTradeAnalysisService(db).ask(current_user["id"], review_id, payload.question)

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
@router.get("/portfolio/summary")
async def get_portfolio_summary(
    environment: Optional[Literal["paper", "live"]] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Expose the same owner-scoped valuation projection that FINN reads."""
    result = await PortfolioToolAdapter(db).execute(user_id=current_user["id"], environment=environment)
    return {"data": result["data"], "as_of": result["as_of"]}


class LiveCashAllocation(BaseModel):
    bot_id: int
    amount_eur: condecimal(ge=Decimal("0"), max_digits=20, decimal_places=2)


class LiveCashAllocationsUpdate(BaseModel):
    allocations: conlist(LiveCashAllocation, max_items=100)


@router.put("/portfolio/live-cash-allocations")
async def update_live_cash_allocations(
    payload: LiveCashAllocationsUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attribute shared free broker EUR to bots for display only."""
    allocation_rate_limiter.check_rate_limit(
        f"owner:{current_user['id']}", limit=3,
        detail="Te veel portfoliotoewijzingen. Probeer het later opnieuw.",
    )
    ip_addr = client_ip(request)
    if ip_addr not in LOCAL_PROXY_IPS:
        allocation_rate_limiter.check_rate_limit(
            f"ip:{ip_addr}", limit=6,
            detail="Te veel portfoliotoewijzingen vanaf dit adres.",
        )
    account = await read_live_account(db, current_user["id"])
    if account is None:
        raise HTTPException(409, "Live-brokerbalans is niet volledig verifieerbaar")
    saved = await replace_allocations(
        db, current_user["id"], account,
        [item.dict() for item in payload.allocations],
    )
    return {"allocations": saved, "exchange": account["exchange_name"],
            "available_cash_eur": account["cash_eur"], "as_of": account["as_of"]}


@router.get("/portfolio/balance-history")
async def get_portfolio_balance_history(
    bucket: str = "1h",
    limit: int = 500,
    is_live: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_portfolio_history(bucket, limit, current_user["id"], is_live)


@router.get("/portfolio/value-history")
async def get_verified_portfolio_value_history(
    environment: Literal["paper", "live"] = "paper",
    bucket: Literal["1h", "1d"] = "1h",
    limit: int = Query(720, ge=1, le=720),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Only complete, versioned Paper EUR snapshots are chartable."""
    if environment == "live":
        return {"environment": environment, "currency": "EUR", "points": [],
                "status": "unreconciled_live", "valuation_version": 2}
    result = await db.execute(text("""
        SELECT ts, equity_eur, cash_eur, position_value_eur,
               covered_bot_count, source_min_at
        FROM (
          SELECT ts, equity_eur, cash_eur, position_value_eur,
                 covered_bot_count, source_min_at
          FROM portfolio_value_snapshots_v2
          WHERE user_id=:user_id AND environment='paper' AND bucket=:bucket
            AND evidence_json <> '{}'::jsonb
            AND NOT EXISTS (
              SELECT 1 FROM bot_configs c
              WHERE c.user_id=:user_id AND c.is_live=FALSE
                AND (EXISTS (
                  SELECT 1 FROM portfolio_unverified_paper_bots u
                  WHERE u.user_id=c.user_id AND u.bot_id=c.id
                ) OR EXISTS (
                  SELECT 1 FROM bot_ledger legacy
                  WHERE legacy.user_id=c.user_id AND legacy.bot_id=c.id
                    AND legacy.entry_type='execute' AND legacy.valuation_version < 2
                ))
            )
          ORDER BY ts DESC LIMIT :limit
        ) recent ORDER BY ts ASC
    """), {"user_id": current_user["id"], "bucket": bucket, "limit": limit})
    points = [dict(row._mapping) for row in result.fetchall()]
    return {"environment": environment, "currency": "EUR", "points": points,
            "status": "available" if points else "no_verified_history", "valuation_version": 2}

@router.get("/bot/balance-history")
async def get_bot_balance_history(
    bot_id: int,
    bucket: str = "1h",
    limit: int = 500,
    current_user: dict = Depends(get_current_user),
    service: BotService = Depends(get_bot_service)
):
    return await service.get_bot_balance_history(bot_id, bucket, limit, current_user["id"])
