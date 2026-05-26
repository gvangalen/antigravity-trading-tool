import logging
import uuid
from datetime import datetime, timedelta, timezone

from backend.infrastructure.repositories.user_repository import UserRepository
from backend.utils.auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from backend.schemas.auth_schema import RegisterRequest, LoginRequest, UserOut

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    @staticmethod
    def _user_out(user) -> UserOut:
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

    @staticmethod
    def _refresh_expiry() -> datetime:
        from backend.utils.auth_utils import REFRESH_TOKEN_EXPIRE_DAYS

        return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    async def _issue_refresh_session(self, user) -> tuple[str, str]:
        refresh_jti = str(uuid.uuid4())
        refresh_payload = {"sub": str(user.id), "role": user.role, "jti": refresh_jti}
        refresh_token = create_refresh_token(refresh_payload)
        await self.repository.create_refresh_session(
            user_id=user.id,
            jti=refresh_jti,
            token_hash=hash_token(refresh_token),
            expires_at=self._refresh_expiry(),
        )
        return refresh_token, refresh_jti

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

        return self._user_out(new_user)

    async def login_user(self, data: LoginRequest):
        user = await self.repository.get_by_email(data.email)
        
        if not user:
            logger.warning(f"❌ Login mislukt: Gebruiker {data.email} niet gevonden in de database.")
            raise ValueError("Onjuiste inloggegevens")
            
        if not user.is_active:
            logger.warning(f"❌ Login mislukt: Gebruiker {data.email} is niet actief.")
            raise ValueError("Onjuiste inloggegevens")

        if not verify_password(data.password, user.password_hash):
            logger.warning(f"❌ Login mislukt: Wachtwoord matcht niet voor {data.email}.")
            raise ValueError("Onjuiste inloggegevens")

        payload = {"sub": str(user.id), "role": user.role}
        access_token = create_access_token(payload)
        refresh_token, _ = await self._issue_refresh_session(user)

        await self.repository.update_last_login(user.id, datetime.utcnow())

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": self._user_out(user)
        }

    async def get_me(self, user_id: int) -> UserOut:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("Gebruiker niet gevonden")
        return self._user_out(user)

    async def refresh_access_token(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise ValueError("Refresh token ongeldig")

        if payload.get("type") != "refresh":
            raise ValueError("Verkeerd token type")

        user_id = int(payload["sub"])
        refresh_jti = payload.get("jti")
        if not refresh_jti:
            raise ValueError("Refresh token mist sessie-id")

        session = await self.repository.get_refresh_session(refresh_jti)
        if not session:
            raise ValueError("Refresh token niet geautoriseerd")

        if session.user_id != user_id:
            raise ValueError("Refresh token hoort niet bij deze gebruiker")

        if session.token_hash != hash_token(refresh_token):
            raise ValueError("Refresh token mismatch")

        now = datetime.now(timezone.utc)
        if session.revoked_at is not None or session.rotated_at is not None:
            raise ValueError("Refresh token is ingetrokken")

        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise ValueError("Refresh token verlopen")

        user = await self.repository.get_by_id(user_id)
        if not user or not user.is_active:
            raise ValueError("Gebruiker niet gevonden of niet actief")

        new_refresh_token, new_refresh_jti = await self._issue_refresh_session(user)
        await self.repository.rotate_refresh_session(
            session,
            replaced_by_jti=new_refresh_jti,
            rotated_at=now,
        )

        return {
            "access_token": create_access_token({"sub": str(user.id), "role": user.role}),
            "refresh_token": new_refresh_token,
        }

    async def revoke_refresh_token(self, refresh_token: str, *, reason: str = "logout") -> bool:
        try:
            payload = decode_token(refresh_token, verify_exp=False)
        except ValueError:
            return False

        if payload.get("type") != "refresh":
            return False

        refresh_jti = payload.get("jti")
        if not refresh_jti:
            return False

        session = await self.repository.get_refresh_session(refresh_jti)
        if not session:
            return False

        if session.token_hash != hash_token(refresh_token):
            return False

        if session.revoked_at is not None:
            return True

        await self.repository.revoke_refresh_session(
            session,
            reason=reason,
            revoked_at=datetime.now(timezone.utc),
        )
        return True
