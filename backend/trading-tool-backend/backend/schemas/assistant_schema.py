from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class AssistantChatRequest(BaseModel):
    query: str
    context: Optional[Dict[str, str]] = None
    timeframe: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = None

class AssistantReasoning(BaseModel):
    confidence_score: float
    risk_detected: bool
    reasons: List[str]
    coaching_level: str

class AssistantChatResponse(BaseModel):
    response: str
    intent: str
    action: Optional[Dict[str, Any]] = None
    draft: Optional[Dict[str, Any]] = None
    state: Optional[Dict[str, Any]] = None
    reasoning: Optional[AssistantReasoning] = None
    trace_id: Optional[str] = None

class AssistantPreferenceUpdate(BaseModel):
    report_style: Optional[str]
    tone: Optional[str]
    detail_level: Optional[str]
    coaching_style: Optional[str]
    experience_level: Optional[str]
    risk_profile: Optional[str]

class AssistantPreferences(BaseModel):
    preferences: Dict[str, str]

class AssistantInsightResponse(BaseModel):
    greeting: str
    bot_insight: Optional[Dict[str, str]] = None
    market_insight: Optional[Dict[str, str]] = None
    context_detected: Optional[Dict[str, str]] = None
