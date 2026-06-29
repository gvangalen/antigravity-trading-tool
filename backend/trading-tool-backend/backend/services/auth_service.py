import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.locale_config import DEFAULT_LOCALE, resolve_locale as resolve_supported_locale
from backend.utils.email_utils import send_email
from backend.utils.auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from backend.schemas.auth_schema import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)

logger = logging.getLogger(__name__)
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "60"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
PASSWORD_RESET_COPY = {
    "nl": {
        "subject": "Reset je Tradamind-wachtwoord",
        "body": (
            "Je hebt een verzoek gedaan om je wachtwoord te resetten.\n\n"
            "Open deze link om een nieuw wachtwoord in te stellen:\n{reset_url}\n\n"
            "Deze link verloopt over {minutes} minuten en kan maar één keer worden gebruikt.\n"
            "Heb je dit niet aangevraagd? Dan kun je deze mail negeren."
        ),
    },
    "en": {
        "subject": "Reset your Tradamind password",
        "body": (
            "You requested a password reset.\n\n"
            "Open this link to set a new password:\n{reset_url}\n\n"
            "This link expires in {minutes} minutes and can only be used once.\n"
            "If you did not request this, you can ignore this email."
        ),
    },
    "de": {
        "subject": "Setze dein Tradamind-Passwort zurück",
        "body": (
            "Du hast ein Zurücksetzen deines Passworts angefordert.\n\n"
            "Öffne diesen Link, um ein neues Passwort festzulegen:\n{reset_url}\n\n"
            "Dieser Link läuft in {minutes} Minuten ab und kann nur einmal verwendet werden.\n"
            "Wenn du das nicht angefordert hast, kannst du diese E-Mail ignorieren."
        ),
    },
}

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
            ai_requests_used_day=user.ai_requests_used_day,
            ai_preferences=user.ai_preferences or {},
        )

    @staticmethod
    def _db_utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def _refresh_expiry(cls) -> datetime:
        from backend.utils.auth_utils import REFRESH_TOKEN_EXPIRE_DAYS

        return cls._db_utc_now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    @classmethod
    def _password_reset_expiry(cls) -> datetime:
        return cls._db_utc_now() + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)

    @staticmethod
    def _password_reset_copy(locale: str) -> dict:
        normalized = resolve_supported_locale(locale)
        return PASSWORD_RESET_COPY.get(normalized) or PASSWORD_RESET_COPY[DEFAULT_LOCALE]

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
        locale = resolve_supported_locale(data.locale)

        new_user = await self.repository.create_user(
            email=data.email,
            password_hash=hashed_pw,
            role=role,
            first_name=data.first_name,
            last_name=data.last_name,
            ai_preferences={"locale": locale},
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

        await self.repository.update_last_login(user.id, self._db_utc_now())
        requested_locale = resolve_supported_locale(data.locale)
        current_locale = resolve_supported_locale((user.ai_preferences or {}).get("locale"))
        if requested_locale != current_locale:
            user = await self.repository.update_ai_preferences(user.id, {"locale": requested_locale}) or user

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": self._user_out(user)
        }

    async def request_password_reset(self, data: ForgotPasswordRequest) -> None:
        locale = resolve_supported_locale(data.locale)
        user = await self.repository.get_by_email(data.email)
        if not user or not user.is_active:
            return

        raw_token = secrets.token_urlsafe(32)
        expires_at = self._password_reset_expiry()

        await self.repository.revoke_password_reset_tokens_for_user(
            user.id,
            reason="replaced",
            revoked_at=self._db_utc_now(),
        )
        await self.repository.create_password_reset_token(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
            locale=locale,
        )

        reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
        copy = self._password_reset_copy(locale)
        body = copy["body"].format(
            reset_url=reset_url,
            minutes=PASSWORD_RESET_EXPIRE_MINUTES,
        )
        send_email(copy["subject"], body, user.email)

    async def validate_password_reset_token(self, raw_token: str) -> bool:
        if not raw_token:
            return False

        token = await self.repository.get_password_reset_token(hash_token(raw_token))
        if not token:
            return False
        if token.used_at is not None or token.revoked_at is not None:
            return False

        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)

    async def reset_password(self, data: ResetPasswordRequest) -> None:
        if not data.password or len(data.password) < 8:
            raise ValueError("Wachtwoord voldoet niet aan minimumlengte")

        token = await self.repository.get_password_reset_token(hash_token(data.token))
        if not token or token.used_at is not None or token.revoked_at is not None:
            raise ValueError("Reset token ongeldig")

        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("Reset token verlopen")

        user = await self.repository.get_by_id(token.user_id)
        if not user or not user.is_active:
            raise ValueError("Gebruiker niet gevonden")

        now = self._db_utc_now()
        await self.repository.update_password_hash(user.id, hash_password(data.password))
        await self.repository.revoke_all_refresh_sessions_for_user(
            user.id,
            reason="password_reset",
            revoked_at=now,
        )
        await self.repository.revoke_password_reset_tokens_for_user(
            user.id,
            reason="password_reset",
            revoked_at=now,
            exclude_token_id=token.id,
        )
        await self.repository.consume_password_reset_token(token, used_at=now)

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
            rotated_at=self._db_utc_now(),
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
            revoked_at=self._db_utc_now(),
        )
        return True
