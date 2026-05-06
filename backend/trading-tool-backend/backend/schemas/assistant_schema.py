from pydantic import BaseModel
from typing import Optional, Dict, Any

class AssistantChatRequest(BaseModel):
    query: str
    context: Optional[Dict[str, str]] = None
    timeframe: Optional[str] = None

class AssistantChatResponse(BaseModel):
    response: str
    intent: str
    action: Optional[Dict[str, Any]] = None

class AssistantPreferenceUpdate(BaseModel):
    report_style: Optional[str]
    tone: Optional[str]
    detail_level: Optional[str]
    coaching_style: Optional[str]

class AssistantPreferences(BaseModel):
    preferences: Dict[str, str]

class AssistantInsightResponse(BaseModel):
    greeting: str
    bot_insight: Optional[Dict[str, str]] = None
    market_insight: Optional[Dict[str, str]] = None
    context_detected: Optional[Dict[str, str]] = None
