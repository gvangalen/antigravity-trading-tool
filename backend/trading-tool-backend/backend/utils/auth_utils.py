import os
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any

import jwt
from jwt import PyJWTError
from fastapi import Cookie, Header, HTTPException, Request, status
import bcrypt
from dotenv import load_dotenv

load_dotenv()
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

# =========================================================
# 🔐 CONFIG
# =========================================================

def _require_secret(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required; refusing to start with an unsafe default secret.")
    if value in {"CHANGE_ME_IN_PRODUCTION", "change-me", "secret", "dev-secret"}:
        raise RuntimeError(f"{name} uses an unsafe default value; configure a strong secret.")
    if len(value) < 32:
        raise RuntimeError(f"{name} must be at least 32 characters.")
    return value


SECRET_KEY = _require_secret("JWT_SECRET_KEY")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# =========================================================
# 🧂 PASSWORD HELPERS
# =========================================================

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), password_hash.encode('utf-8'))


# =========================================================
# 🎫 JWT HELPERS
# =========================================================

def create_token(data: Dict[str, Any], expires_delta: timedelta, token_type: str):
    now = datetime.now(timezone.utc)

    payload = data.copy()
    payload.update({
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    })

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: Dict[str, Any]):
    return create_token(
        data=data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(data: Dict[str, Any]):
    return create_token(
        data=data,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


CAPACITY_FIXTURE_ROUTES = frozenset({
    "/api/auth/me",
    "/api/workspace/asset",
    "/api/assistant/v2/conversations",
    "/api/bot/trade-reviews",
})


FINN_TEMP_QA_KIND = "manual_trade_temporary_v1"
FINN_TEMP_QA_ROUTE_RULES = (
    ("GET", re.compile(r"/api/auth/me")),
    ("POST", re.compile(r"/api/assistant/v2/runs")),
    ("GET", re.compile(r"/api/assistant/v2/runs/[A-Za-z0-9_-]+")),
    ("GET", re.compile(r"/api/assistant/v2/runs/[A-Za-z0-9_-]+/stream")),
    ("POST", re.compile(r"/api/assistant/v2/runs/[A-Za-z0-9_-]+/cancel")),
    ("GET", re.compile(r"/api/assistant/v2/proposals/[A-Za-z0-9_-]+")),
    ("POST", re.compile(r"/api/assistant/v2/proposals/[A-Za-z0-9_-]+/(?:publish|confirm|execute)")),
)
FINN_TEMP_QA_PROPOSAL_WRITE = re.compile(
    r"/api/assistant/v2/proposals/([A-Za-z0-9_-]+)/(?:publish|confirm|execute)")


async def _validate_finn_temp_qa_token(payload: Dict[str, Any], request: Request,
                                       *, bearer_token: str | None,
                                       selected_token: str) -> None:
    """A temporary QA bearer is valid only while its owner-bound lease is active."""
    from sqlalchemy import select
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.models import FinnV2Proposal, User

    fixture = payload.get("finn_temp_qa")
    if (not bearer_token or selected_token != bearer_token or not isinstance(fixture, dict)
            or fixture.get("kind") != FINN_TEMP_QA_KIND
            or not isinstance(fixture.get("namespace"), str)
            or not isinstance(fixture.get("lease"), str)
            or not any(method == request.method and rule.fullmatch(request.url.path)
                       for method, rule in FINN_TEMP_QA_ROUTE_RULES)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Temporary QA token is restricted to FINN test routes")
    try:
        subject = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Temporary QA token subject invalid")
    proposal_match = (FINN_TEMP_QA_PROPOSAL_WRITE.fullmatch(request.url.path)
                      if request.method == "POST" else None)
    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.id == subject))).scalar_one_or_none()
        proposal = None
        if proposal_match is not None:
            proposal = (await session.execute(select(FinnV2Proposal).where(
                FinnV2Proposal.id == proposal_match.group(1),
                FinnV2Proposal.user_id == subject))).scalar_one_or_none()
    preferences = user.ai_preferences if user is not None else None
    lease = preferences.get("finn_temp_qa") if isinstance(preferences, dict) else None
    if (user is None or user.is_active is not True or user.role != "user"
            or not isinstance(preferences, dict)
            or preferences.get("qa_fixture") != FINN_TEMP_QA_KIND
            or not isinstance(lease, dict)
            or lease.get("namespace") != fixture["namespace"]
            or lease.get("lease") != fixture["lease"]
            or lease.get("status") != "active"
            or not isinstance(lease.get("expires_at"), str)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Temporary QA lease inactive")
    try:
        expiry = datetime.fromisoformat(lease["expires_at"])
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("expired")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Temporary QA lease expired")
    if proposal_match is not None and (
            proposal is None or proposal.operation_type != "create_manual_trade_plan"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Temporary QA token permits only manual trade plans")


def decode_token(token: str, *, verify_exp: bool = True,
                 allow_capacity_fixture: bool = False,
                 allow_finn_temp_qa: bool = False) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": verify_exp},
        )
    except PyJWTError as e:
        raise ValueError(f"Invalid token: {e}")
    if "capacity_fixture" in payload and not allow_capacity_fixture:
        raise ValueError("Capacity fixture token is not valid for this operation")
    if "finn_temp_qa" in payload and not allow_finn_temp_qa:
        raise ValueError("Temporary QA token is not valid for this operation")
    return payload


# =========================================================
# 👤 CURRENT USER VIA COOKIE
# =========================================================

async def get_current_user(
    request: Request,
    access_token: str = Cookie(default=None),
    authorization: str = Header(default=None),
):
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    token = access_token or bearer_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
        )

    try:
        payload = decode_token(token, allow_capacity_fixture=True, allow_finn_temp_qa=True)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    if "capacity_fixture" in payload:
        fixture = payload["capacity_fixture"]
        if (
            not isinstance(fixture, dict)
            or fixture.get("kind") != "read_only_load_v1"
            or request.method != "GET"
            or request.url.path not in CAPACITY_FIXTURE_ROUTES
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Capacity fixture token is restricted to read-only load routes")

    if "finn_temp_qa" in payload:
        await _validate_finn_temp_qa_token(payload, request, bearer_token=bearer_token,
                                           selected_token=token)

    return {
        "id": int(user_id),
        "role": payload.get("role")
    }
