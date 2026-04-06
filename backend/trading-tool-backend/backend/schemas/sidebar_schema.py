from pydantic import BaseModel

class ActiveTradeResponse(BaseModel):
    id: int
    symbol: str
    status: str

class BotStatusResponse(BaseModel):
    state: str
    strategy: str
    updated: str
