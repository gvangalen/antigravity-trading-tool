from pydantic import BaseModel
from typing import Optional, Any

class CeleryTaskResponse(BaseModel):
    task_id: str
    state: str
    result: Optional[Any] = None
    error: Optional[str] = None
