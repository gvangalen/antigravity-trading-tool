import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Body, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.utils.rate_limit import InMemoryRateLimiter, client_ip
from backend.schemas.auth_schema import LoginRequest, RegisterRequest, RefreshRequest, UserOut
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.auth_service import AuthService
from backend.utils.system_logger import sys_logger

# =========================================================
# ⚙️ Router
# =========================================================
router = APIRouter()
logger = logging.getLogger(__name__)

# =========================================================
# 🍪 COOKIE SETTINGS (DYNAMISCH VOOR HTTP/HTTPS)
# =========================================================
frontend_url = os.getenv("FRONTEND_URL", "")
is_https = frontend_url.startswith("https")

# Voor productie (HTTPS) gebruiken we 'none' voor maximale compatibiliteit cross-origin
# Voor lokale development (HTTP) gebruiken we 'lax' omdat 'none' secure=True vereist
# WE FORCEEREN LAX ALS WE OP LOCALHOST ZITTEN OM INLOGPROBLEMEN TE VOORKOMEN
is_localhost = "localhost" in frontend_url or "127.0.0.1" in frontend_url
is_prod_https = is_https and not is_localhost

samesite_val = "none" if is_prod_https else "lax"
cookie_domain = ".tradamind.com" if is_prod_https and "tradamind.com" in frontend_url else None

COOKIE_SETTINGS = dict(
    httponly=True,
    secure=is_prod_https,    # ⭐ Alleen verplicht op echte HTTPS prod
    samesite=samesite_val,
    domain=cookie_domain,
    path="/",
)

auth_rate_limiter = InMemoryRateLimiter(requests_limit=10, window_seconds=300)
AUTH_LOGIN_EMAIL_LIMIT = 6
AUTH_LOGIN_IP_LIMIT = 20
AUTH_REFRESH_IP_LIMIT = 30


def _auth_client_mode(x_tradamind_client: Optional[str]) -> str:
    client = (x_tradamind_client or "").strip().lower()
    return "mobile" if client in {"mobile-expo", "mobile", "native"} else "web"


def _login_response_payload(result: dict, client_mode: str) -> dict:
    payload = {
        "success": True,
        "user": result["user"].dict(),
        "auth_mode": client_mode,
        "token_transport": "body+cookie" if client_mode == "mobile" else "cookie",
    }
    if client_mode == "mobile":
        payload["access_token"] = result["access_token"]
        payload["refresh_token"] = result["refresh_token"]
    return payload


def _apply_auth_login_rate_limit(raw_request: Request, email: str) -> None:
    ip_addr = client_ip(raw_request)
    auth_rate_limiter.check_rate_limit(
        f"auth_login_email:{email.lower()}",
        limit=AUTH_LOGIN_EMAIL_LIMIT,
        detail="Te veel loginpogingen. Wacht kort en probeer opnieuw.",
    )
    auth_rate_limiter.check_rate_limit(
        f"auth_login_ip:{ip_addr}",
        limit=AUTH_LOGIN_IP_LIMIT,
        detail="Te veel loginpogingen vanaf dit IP-adres. Wacht kort en probeer opnieuw.",
    )


def _apply_auth_refresh_rate_limit(raw_request: Request) -> None:
    ip_addr = client_ip(raw_request)
    auth_rate_limiter.check_rate_limit(
        f"auth_refresh_ip:{ip_addr}",
        limit=AUTH_REFRESH_IP_LIMIT,
        detail="Te veel refresh-verzoeken. Wacht kort en probeer opnieuw.",
    )


def _safe_auth_error(message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)

async def get_auth_service(db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    return AuthService(repo)


# =========================================================
# 🧪 REGISTER
# =========================================================

@router.post("/auth/register", response_model=UserOut)
async def register_user(
    body: RegisterRequest,
    service: AuthService = Depends(get_auth_service)
):
    try:
        user = await service.register_user(body)
        sys_logger.log_info(f"User registered: {body.email}", source="auth", endpoint="/auth/register")
        return user
    except ValueError as e:
        sys_logger.log_warning(f"Registration failed: {str(e)}", source="auth", endpoint="/auth/register", metadata={"email": body.email})
        raise _safe_auth_error("Registratie mislukt.", 400)
    except Exception as e:
        sys_logger.log_error(f"Critical registration error: {str(e)}", source="auth", endpoint="/auth/register", metadata={"email": body.email})
        logger.exception("❌ Error opgetreden bij registratie")
        raise HTTPException(status_code=500, detail="Gebruiker kan niet worden aangemaakt")


# =========================================================
# 🔐 LOGIN (cookies!)
# =========================================================

@router.post("/auth/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    x_tradamind_client: Optional[str] = Header(default=None, alias="X-Tradamind-Client"),
):
    try:
        _apply_auth_login_rate_limit(request, body.email)
        result = await service.login_user(body)
        client_mode = _auth_client_mode(x_tradamind_client)
        
        # Cookies plaatsen
        response.set_cookie(
            "access_token",
            result["access_token"],
            max_age=60 * 60,
            **COOKIE_SETTINGS,
        )
        response.set_cookie(
            "refresh_token",
            result["refresh_token"],
            max_age=60 * 60 * 24 * 7,
            **COOKIE_SETTINGS,
        )

        sys_logger.log_info(f"User logged in: {body.email}", source="auth", endpoint="/auth/login", user_id=result["user"].id)

        return _login_response_payload(result, client_mode)

    except ValueError as e:
        sys_logger.log_warning(f"Login failed for {body.email}: {str(e)}", source="auth", endpoint="/auth/login")
        raise _safe_auth_error("Ongeldige inloggegevens.", 401)
    except Exception as e:
        sys_logger.log_error(f"Critical login error for {body.email}: {str(e)}", source="auth", endpoint="/auth/login")
        logger.exception("❌ Fout tijdens login")
        raise _safe_auth_error("Interne authenticatiefout.", 500)


# =========================================================
# 🔁 REFRESH TOKEN
# =========================================================

@router.post("/auth/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None),
    body: Optional[RefreshRequest] = Body(default=None),
    service: AuthService = Depends(get_auth_service),
    x_tradamind_client: Optional[str] = Header(default=None, alias="X-Tradamind-Client"),
):
    _apply_auth_refresh_rate_limit(request)
    token = refresh_token or (body.refresh_token if body else None)

    if not token:
        raise HTTPException(status_code=401, detail="Geen refresh token")

    try:
        tokens = await service.refresh_access_token(token)
        client_mode = _auth_client_mode(x_tradamind_client)

        refresh_payload = {"success": True, "auth_mode": client_mode}
        if client_mode == "mobile":
            refresh_payload["access_token"] = tokens["access_token"]
            refresh_payload["refresh_token"] = tokens["refresh_token"]
        resp = JSONResponse(refresh_payload)
        resp.set_cookie(
            "access_token",
            tokens["access_token"],
            max_age=60 * 60,
            **COOKIE_SETTINGS,
        )
        resp.set_cookie(
            "refresh_token",
            tokens["refresh_token"],
            max_age=60 * 60 * 24 * 7,
            **COOKIE_SETTINGS,
        )
        return resp
        
    except ValueError as e:
        raise _safe_auth_error("Ongeldige refresh token.", 401)
    except Exception as e:
        logger.exception("❌ Error bij refresh token")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# =========================================================
# 🚪 LOGOUT
# =========================================================

@router.post("/auth/logout")
async def logout(
    refresh_token: Optional[str] = Cookie(default=None),
    body: Optional[RefreshRequest] = Body(default=None),
    service: AuthService = Depends(get_auth_service),
):
    token = refresh_token or (body.refresh_token if body else None)
    if token:
        await service.revoke_refresh_token(token, reason="logout")

    resp = JSONResponse({"success": True})
    
    # We proberen de cookies op meerdere manieren te wissen om 'sticky sessions'
    # op verschillende (sub)domeinen te voorkomen.
    
    # 1. Voor het geconfigureerde domein (.tradamind.com)
    for cookie_name in ["access_token", "refresh_token"]:
        resp.delete_cookie(
            cookie_name, 
            path="/",
            domain=COOKIE_SETTINGS.get("domain")
        )
        
        # 2. Voor het naked domain (zonder punt) als extra backup
        resp.delete_cookie(
            cookie_name, 
            path="/",
            domain="tradamind.com"
        )

        # 3. Zonder specifiek domein (host-only)
        resp.delete_cookie(
            cookie_name, 
            path="/"
        )
        
    return resp


# =========================================================
# 👤 AUTH / ME
# =========================================================

@router.get("/auth/me", response_model=UserOut)
async def get_me(
    current_user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_me(user_id)
    except ValueError as e:
        raise _safe_auth_error("Gebruiker niet gevonden.", 404)
    except Exception as e:
        logger.exception("❌ Fout bij get_me")
        raise HTTPException(status_code=500, detail="Internal Server Error")
