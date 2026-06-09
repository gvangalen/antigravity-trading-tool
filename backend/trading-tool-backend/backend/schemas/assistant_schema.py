from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class AssistantContextSchema(BaseModel):
    page: Optional[str] = None
    page_type: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    bot_id: Optional[int] = None
    setup_id: Optional[int] = None
    setup_type: Optional[str] = None
    setup_symbol: Optional[str] = None
    setup_timeframe: Optional[str] = None
    strategy_id: Optional[int] = None
    setup_name: Optional[str] = None
    finn_draft: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"

class AssistantChatRequest(BaseModel):
    query: str
    context: Optional[AssistantContextSchema] = None
    timeframe: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None  # Optional session ID for persistent chats

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
    suggested_actions: Optional[List[str]] = None
    session_id: Optional[str] = None  # Return session ID to the client
    flow: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list)
    invalid_fields: List[Dict[str, Any]] = Field(default_factory=list)
    next_question: Optional[str] = None
    can_confirm: bool = False
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    risk_summary: Optional[str] = None
    next_best_action: Optional[str] = None
    review_reason: Optional[str] = None

class AssistantActionExecuteRequest(BaseModel):
    action: Dict[str, Any]

class AssistantActionExecuteResponse(BaseModel):
    ok: bool
    message: str
    setup_id: Optional[int] = None
    strategy_id: Optional[int] = None
    bot_id: Optional[int] = None
    draft: Optional[Dict[str, Any]] = None

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
    context_detected: Optional[Dict[str, Any]] = None
    suggested_actions: Optional[List[str]] = None  # Server-Driven proactive action chips


class AssistantAnalyticsEvent(BaseModel):
    event_name: str
    session_id: Optional[str] = None
    surface: str = "unknown"
    page: Optional[str] = None
    asset: Optional[str] = None
    flow_type: Optional[str] = None
    action_type: Optional[str] = None
    report_type: Optional[str] = None
    decision_id: Optional[str] = None
    bot_id: Optional[int] = None
    setup_id: Optional[int] = None
    strategy_id: Optional[int] = None
    trace_id: Optional[str] = None
    prompt_text: Optional[str] = None
    next_best_action: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

# =====================================================
# Chat Session Management schemas
# =====================================================

class ChatSessionResponse(BaseModel):
    id: str
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    intent: Optional[str] = None
    actions: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True

class ChatSessionDetailResponse(BaseModel):
    session: ChatSessionResponse
    messages: List[ChatMessageResponse]
