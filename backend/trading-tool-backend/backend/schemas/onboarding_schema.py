from typing import Dict, List, Optional

from pydantic import BaseModel

class StepRequest(BaseModel):
    step: str

class OnboardingStatusResponse(BaseModel):
    has_profile: bool
    has_asset: bool
    has_market: bool
    has_macro: bool
    has_technical: bool
    has_setup: bool
    has_strategy: bool
    has_bot: bool
    onboarding_complete: bool
    pipeline_started: bool
    active_asset: Optional[str] = None
    current_phase: str = "profile"
    next_action: str = "complete_profile"
    next_route: str = "/onboarding/profile"
    phases_completed: Dict[str, bool] = {}
    phases_unlocked: Dict[str, bool] = {}
    phase_missing: Dict[str, List[str]] = {}
    optional_missing: Dict[str, List[str]] = {}
