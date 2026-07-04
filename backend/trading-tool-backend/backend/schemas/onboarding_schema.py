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
