"""Read-only feed and explicit owner-scoped state changes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from backend.infrastructure.database import get_db
from backend.services.finn_coach_feed_service import FinnCoachFeedService
from backend.utils.auth_utils import get_current_user

router = APIRouter()


def _locale(value: str | None) -> str:
    language = str(value or "nl").lower().split("-", 1)[0]
    return language if language in {"nl", "en", "de"} else "nl"


@router.get("/assistant/feed")
async def list_feed(history: bool = False, limit: int = Query(50, ge=1, le=100),
                    before_created_at: datetime | None = None, before_id: UUID | None = None,
                    x_locale: str | None = Header(None),
                    current_user: dict = Depends(get_current_user), session=Depends(get_db)):
    if bool(before_created_at) != bool(before_id) or (before_id and not history):
        raise HTTPException(status_code=422, detail="Ongeldige feedpaginering")
    return await FinnCoachFeedService(session).list(
        user_id=current_user["id"], locale=_locale(x_locale), history=history, limit=limit,
        before_created_at=before_created_at, before_id=str(before_id) if before_id else None,
    )


@router.get("/assistant/feed/{item_id}")
async def feed_detail(item_id: str, x_locale: str | None = Header(None),
                      current_user: dict = Depends(get_current_user), session=Depends(get_db)):
    item = await FinnCoachFeedService(session).detail(
        user_id=current_user["id"], item_id=item_id, locale=_locale(x_locale),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Feeditem niet gevonden")
    return item


@router.post("/assistant/feed/{item_id}/{action}")
async def update_feed_status(item_id: str, action: str,
                             current_user: dict = Depends(get_current_user), session=Depends(get_db)):
    if action not in {"read", "handled", "archived"}:
        raise HTTPException(status_code=404, detail="Feedactie niet gevonden")
    changed = await FinnCoachFeedService(session).set_status(
        user_id=current_user["id"], item_id=item_id,
        status={"read": "read", "handled": "handled", "archived": "archived"}[action],
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Feeditem niet gevonden of niet actief")
    return {"id": item_id, "status": action}
