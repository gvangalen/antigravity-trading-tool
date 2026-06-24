from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class RegisterRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    is_active: bool
    first_name: Optional[str]
    last_name: Optional[str]
    ai_plan: Optional[str]
    ai_requests_limit_day: Optional[int]
    ai_requests_used_day: Optional[int]
    ai_preferences: Optional[Dict[str, Any]] = None
