from pydantic import BaseModel, root_validator, Field, Extra, validator
from typing import Optional, List, Dict, Any
from datetime import date, datetime


def _canonical_bot_cadence(value):
    if value is None:
        return None
    aliases = {
        "hourly": "hourly", "ieder uur": "hourly", "stündlich": "hourly",
        "daily": "daily", "dagelijks": "daily", "täglich": "daily",
        "weekly": "weekly", "wekelijks": "weekly", "wöchentlich": "weekly",
        "monthly": "monthly", "maandelijks": "monthly", "monatlich": "monthly",
    }
    return aliases.get(str(value).strip().casefold(), value)

class BotConfigCreateSchema(BaseModel):
    name: str
    strategy_id: int
    mode: str = "manual"
    is_live: bool = False
    risk_profile: str = "balanced"
    budget_total_eur: float = 0.0
    budget_daily_limit_eur: float = 0.0
    budget_min_order_eur: float = 0.0
    budget_max_order_eur: float = 0.0
    max_asset_exposure_pct: float = 100.0
    cadence: str = "daily"
    base_currency: str = "EUR"
    symbol: Optional[str] = None

    _normalize_cadence = validator("cadence", pre=True, allow_reuse=True)(_canonical_bot_cadence)

class BotConfigUpdateSchema(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    is_live: Optional[bool] = None
    risk_profile: Optional[str] = None
    is_active: Optional[bool] = None
    budget_total_eur: Optional[float] = None
    budget_daily_limit_eur: Optional[float] = None
    budget_min_order_eur: Optional[float] = None
    budget_max_order_eur: Optional[float] = None
    max_asset_exposure_pct: Optional[float] = None
    cadence: Optional[str] = None
    base_currency: Optional[str] = None
    
    # Aliases
    total_eur: Optional[float] = None
    daily_limit_eur: Optional[float] = None
    min_order_eur: Optional[float] = None
    max_order_eur: Optional[float] = None
    risk_acknowledged: Optional[bool] = None

    _normalize_cadence = validator("cadence", pre=True, allow_reuse=True)(_canonical_bot_cadence)
    
class BotManualOrderSchema(BaseModel):
    bot_id: int
    symbol: str = "BTC"
    side: str
    quantity: float
    price: float
    value_eur: Optional[float] = None
    idempotency_key: Optional[str] = None
    risk_acknowledged: bool = False
    live_preflight_token: Optional[str] = None
    live_preflight_action_id: Optional[str] = None
    setup_block_acknowledged: bool = False

class TradePlanUpsertSchema(BaseModel):
    entry_plan: List[Dict[str, Any]] = []
    stop_loss: Dict[str, Any] = {}
    targets: List[Dict[str, Any]] = []
    risk: Dict[str, Any] = {}

class BotGenerateTodaySchema(BaseModel):
    bot_id: int
    report_date: Optional[str] = None

class BotSkipSchema(BaseModel):
    bot_id: int
    report_date: Optional[str] = None

class BotMarkExecutedSchema(BaseModel):
    bot_id: int
    decision_id: int
