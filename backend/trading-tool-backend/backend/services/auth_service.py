from datetime import datetime, timezone

from backend.infrastructure.repositories.user_repository import UserRepository
from backend.utils.auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from backend.schemas.auth_schema import RegisterRequest, LoginRequest, UserOut

class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def register_user(self, data: RegisterRequest) -> UserOut:
        existing = await self.repository.get_by_email(data.email)
        if existing:
            raise ValueError("E-mail bestaat al")

        count = await self.repository.count_users()
        role = "admin" if count == 0 else "user"
        hashed_pw = hash_password(data.password)

        new_user = await self.repository.create_user(
            email=data.email,
            password_hash=hashed_pw,
            role=role,
            first_name=data.first_name,
            last_name=data.last_name
        )

        return UserOut(
            id=new_user.id,
            email=new_user.email,
            role=new_user.role,
            is_active=new_user.is_active,
            first_name=new_user.first_name,
            last_name=new_user.last_name,
            ai_plan=new_user.ai_plan,
            ai_requests_limit_day=new_user.ai_requests_limit_day,
            ai_requests_used_day=new_user.ai_requests_used_day
        )

    async def login_user(self, data: LoginRequest):
        user = await self.repository.get_by_email(data.email)
        
        if not user or not user.is_active:
            raise ValueError("Onjuiste inloggegevens")

        if not verify_password(data.password, user.password_hash):
            raise ValueError("Onjuiste inloggegevens")

        payload = {"sub": str(user.id), "role": user.role}
        access_token = create_access_token(payload)
        refresh_token = create_refresh_token(payload)

        await self.repository.update_last_login(user.id, datetime.utcnow())

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": UserOut(
                id=user.id,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                first_name=user.first_name,
                last_name=user.last_name,
                ai_plan=user.ai_plan,
                ai_requests_limit_day=user.ai_requests_limit_day,
                ai_requests_used_day=user.ai_requests_used_day
            )
        }

    async def get_me(self, user_id: int) -> UserOut:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("Gebruiker niet gevonden")
        return UserOut(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            first_name=user.first_name,
            last_name=user.last_name,
            ai_plan=user.ai_plan,
            ai_requests_limit_day=user.ai_requests_limit_day,
            ai_requests_used_day=user.ai_requests_used_day
        )

    async def refresh_access_token(self, refresh_token: str) -> str:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise ValueError("Refresh token ongeldig")

        if payload.get("type") != "refresh":
            raise ValueError("Verkeerd token type")

        user_id = int(payload["sub"])
        user = await self.repository.get_by_id(user_id)
        if not user or not user.is_active:
            raise ValueError("Gebruiker niet gevonden of niet actief")

        return create_access_token({"sub": str(user.id), "role": user.role})
