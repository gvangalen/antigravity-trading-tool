from pydantic import BaseModel
from typing import Optional

class BootstrapAgentsResponse(BaseModel):
    status: str
    message: str
    user_id: int
