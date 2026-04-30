from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ExchangeKeySchema(BaseModel):
    exchange_name: str
    api_key: str
    api_secret: str
    api_passphrase: Optional[str] = None

class ExchangeBalanceResponse(BaseModel):
    exchange: str
    total: Dict[str, float]
    free: Dict[str, float]
    used: Dict[str, float]
    total_eur: float = 0.0

class ExchangeStatusResponse(BaseModel):
    exchange: str
    is_connected: bool
    message: Optional[str] = None
