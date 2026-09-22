from pydantic import BaseModel, root_validator, Field, Extra
from typing import Optional, List, Dict, Any

# =======================================================
# SETUPS
# =======================================================
class SetupCreateSchema(BaseModel):
    name: str = Field(..., description="Name of the setup")
    symbol: str = Field(..., description="Target symbol/ticker")
    setup_type: str = Field(..., description="Type of setup (e.g. dca, trade)")

    @root_validator
    def validate_dca_schedule(cls, values):
        if str(values.get("setup_type") or "").casefold() != "dca":
            return values
        frequency = str(values.get("dca_frequency") or "").casefold()
        if frequency not in {"daily", "weekly", "monthly"}:
            raise ValueError("dca_frequency must be daily, weekly, or monthly")
        if frequency == "weekly" and values.get("dca_day") in {None, ""}:
            raise ValueError("dca_day is required for a weekly DCA setup")
        if frequency == "monthly" and values.get("dca_month_day") in {None, ""}:
            raise ValueError("dca_month_day is required for a monthly DCA setup")
        return values
    
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
    # A strategy can intentionally differ from its parent setup. When these
    # fields are omitted the service records the setup-derived default source.
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    
    class Config:
        extra = Extra.allow
