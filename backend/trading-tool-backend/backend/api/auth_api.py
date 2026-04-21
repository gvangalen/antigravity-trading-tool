import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.auth_schema import LoginRequest, RegisterRequest, UserOut
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.auth_service import AuthService

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

# Voor HTTPS gebruiken we 'none' voor maximale compatibiliteit cross-origin
# Voor HTTP gebruiken we 'lax' omdat 'none' secure=True vereist
samesite_val = "none" if is_https else "lax"

# Optioneel: wildcard domain voor cookies op zowel www als root
cookie_domain = "tradamind.com" if is_https and "tradamind.com" in frontend_url else None

COOKIE_SETTINGS = dict(
    httponly=True,
    secure=is_https,    # ⭐ Verplicht op HTTPS
    samesite=samesite_val,
    domain=cookie_domain,
    path="/",
)

def get_auth_service(db: AsyncSession = Depends(get_db)):
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
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("❌ Error opgetreden bij registratie")
        raise HTTPException(status_code=500, detail="Gebruiker kan niet worden aangemaakt")


# =========================================================
# 🔐 LOGIN (cookies!)
# =========================================================

@router.post("/auth/login")
async def login(
    body: LoginRequest, 
    response: Response,
    service: AuthService = Depends(get_auth_service)
):
    try:
        result = await service.login_user(body)
        
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

        return {
            "success": True,
            "user": result["user"].dict()
        }

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("❌ Fout tijdens login")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


# =========================================================
# 🔁 REFRESH TOKEN
# =========================================================

@router.post("/auth/refresh")
async def refresh_token(
    response: Response, 
    refresh_token: Optional[str] = Cookie(default=None),
    service: AuthService = Depends(get_auth_service)
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Geen refresh token")

    try:
        new_access = await service.refresh_access_token(refresh_token)

        resp = JSONResponse({"success": True})
        resp.set_cookie(
            "access_token",
            new_access,
            max_age=60 * 60,
            **COOKIE_SETTINGS,
        )
        return resp
        
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("❌ Error bij refresh token")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# =========================================================
# 🚪 LOGOUT
# =========================================================

@router.post("/auth/logout")
async def logout(response: Response):
    resp = JSONResponse({"success": True})
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/")
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("❌ Fout bij get_me")
        raise HTTPException(status_code=500, detail="Internal Server Error")
