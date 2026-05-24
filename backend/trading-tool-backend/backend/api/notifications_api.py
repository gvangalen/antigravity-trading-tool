from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.infrastructure.models import PushSubscription, MobilePushToken
from backend.utils.auth_utils import get_current_user
from pydantic import BaseModel
from typing import Optional
from loguru import logger

router = APIRouter(prefix="/notifications", tags=["notifications"])

class SubscriptionInfo(BaseModel):
    endpoint: str
    keys: dict

class SubscribeRequest(BaseModel):
    subscription: SubscriptionInfo
    user_id: Optional[int] = None

@router.post("/subscribe")
async def subscribe(
    request: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user["id"])
    try:
        result = await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == request.subscription.endpoint)
        )
        existing = result.scalars().first()

        if existing:
            existing.user_id = user_id
            existing.p256dh = request.subscription.keys.get("p256dh")
            existing.auth = request.subscription.keys.get("auth")
        else:
            new_sub = PushSubscription(
                user_id=user_id,
                endpoint=request.subscription.endpoint,
                p256dh=request.subscription.keys.get("p256dh"),
                auth=request.subscription.keys.get("auth")
            )
            db.add(new_sub)
        
        await db.commit()
        return {"status": "success", "message": "Subscribed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in subscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not subscribe")

@router.post("/unsubscribe")
async def unsubscribe(
    endpoint: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user["id"])
    try:
        await db.execute(
            delete(PushSubscription).where(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == user_id,
            )
        )
        await db.commit()
        return {"status": "success", "message": "Unsubscribed successfully"}
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in unsubscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not unsubscribe")


# =========================================================================
# NATIVE MOBILE PUSH NOTIFICATIONS (EXPO PUSH TOKENS)
# =========================================================================

class MobileSubscribeRequest(BaseModel):
    push_token: str
    device_name: Optional[str] = None
    user_id: Optional[int] = None

class MobileUnsubscribeRequest(BaseModel):
    push_token: str

@router.post("/mobile/subscribe")
async def mobile_subscribe(
    request: MobileSubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user["id"])
    try:
        result = await db.execute(
            select(MobilePushToken).where(MobilePushToken.push_token == request.push_token)
        )
        existing = result.scalars().first()

        if existing:
            existing.user_id = user_id
            if request.device_name:
                existing.device_name = request.device_name
        else:
            new_token = MobilePushToken(
                user_id=user_id,
                push_token=request.push_token,
                device_name=request.device_name
            )
            db.add(new_token)
        
        await db.commit()
        return {"status": "success", "message": "Mobile push token registered successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in mobile subscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not subscribe mobile token")

@router.post("/mobile/unsubscribe")
async def mobile_unsubscribe(
    request: MobileUnsubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(current_user["id"])
    try:
        await db.execute(
            delete(MobilePushToken).where(
                MobilePushToken.push_token == request.push_token,
                MobilePushToken.user_id == user_id,
            )
        )
        await db.commit()
        return {"status": "success", "message": "Mobile token unsubscribed successfully"}
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error in mobile unsubscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not unsubscribe mobile token")
