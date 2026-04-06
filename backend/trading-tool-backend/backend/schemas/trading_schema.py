from pydantic import BaseModel, root_validator, Field, Extra
from typing import Optional, List, Dict, Any

# =======================================================
# SETUPS
# =======================================================
class SetupCreateSchema(BaseModel):
    name: str = Field(..., description="Name of the setup")
    symbol: str = Field(..., description="Target symbol/ticker")
    setup_type: str = Field(..., description="Type of setup (e.g. dca, trade)")
    
    # Extra flex fields get packed into the BaseModel automatically if configured
    # Or explicitly passed via kwargs in route
    class Config:
        extra = Extra.allow  # This ensures any other keys passed are accepted to easily dump into JSON/fields

# =======================================================
# STRATEGIES
# =======================================================
class StrategyCreateSchema(BaseModel):
    setup_id: int = Field(..., description="ID of the parent setup")
    execution_mode: str = Field(..., description="Execution mode (fixed, custom)")
    base_amount: float = Field(..., description="Base investment amount")
    
    # Optional explicitly defined standard fields
    name: Optional[str] = None
    
    class Config:
        extra = Extra.allow
