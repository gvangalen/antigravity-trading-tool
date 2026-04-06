from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class AgentInsightSchema(BaseModel):
    score: Optional[float]
    trend: Optional[str]
    bias: Optional[str]
    risk: Optional[str]
    summary: Optional[str]
    top_signals: List[Any]
    date: Optional[str]
    created_at: Optional[str]

class AgentInsightResponse(BaseModel):
    insight: Optional[AgentInsightSchema]

class AgentReflectionSchema(BaseModel):
    indicator: str
    raw_score: Optional[float]
    ai_score: Optional[float]
    compliance: Optional[float]
    comment: Optional[str]
    recommendation: Optional[str]
    date: Optional[str]
    timestamp: Optional[str]

class AgentReflectionResponse(BaseModel):
    reflections: List[AgentReflectionSchema]

class CeleryTaskResponse(BaseModel):
    task_id: str
    state: str
    result: Optional[Any] = None
    error: Optional[str] = None
