from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.infrastructure.database import get_db
from backend.infrastructure.models import PushSubscription, User, MobilePushToken
from pydantic import BaseModel
from typing import Optional
from loguru import logger

router = APIRouter(prefix="/notifications", tags=["notifications"])

class SubscriptionInfo(BaseModel):
    endpoint: str
    keys: dict

class SubscribeRequest(BaseModel):
    user_id: int
    subscription: SubscriptionInfo

@router.post("/subscribe")
async def subscribe(request: SubscribeRequest, db: Session = Depends(get_db)):
    try:
        # Check if already exists
        existing = db.query(PushSubscription).filter(PushSubscription.endpoint == request.subscription.endpoint).first()
        
        # User validation (optional but good)
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if existing:
            existing.user_id = request.user_id
            existing.p256dh = request.subscription.keys.get("p256dh")
            existing.auth = request.subscription.keys.get("auth")
        else:
            new_sub = PushSubscription(
                user_id=request.user_id,
                endpoint=request.subscription.endpoint,
                p256dh=request.subscription.keys.get("p256dh"),
                auth=request.subscription.keys.get("auth")
            )
            db.add(new_sub)
        
        db.commit()
        return {"status": "success", "message": "Subscribed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error in subscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not subscribe")

@router.post("/unsubscribe")
async def unsubscribe(endpoint: str, db: Session = Depends(get_db)):
    try:
        db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).delete()
        db.commit()
        return {"status": "success", "message": "Unsubscribed successfully"}
    except Exception as e:
        db.rollback()
        logger.exception(f"Error in unsubscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not unsubscribe")


# =========================================================================
# NATIVE MOBILE PUSH NOTIFICATIONS (EXPO PUSH TOKENS)
# =========================================================================

class MobileSubscribeRequest(BaseModel):
    user_id: int
    push_token: str
    device_name: Optional[str] = None

class MobileUnsubscribeRequest(BaseModel):
    push_token: str

@router.post("/mobile/subscribe")
async def mobile_subscribe(request: MobileSubscribeRequest, db: Session = Depends(get_db)):
    try:
        # Check if already exists
        existing = db.query(MobilePushToken).filter(MobilePushToken.push_token == request.push_token).first()
        
        # User validation
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if existing:
            existing.user_id = request.user_id
            if request.device_name:
                existing.device_name = request.device_name
        else:
            new_token = MobilePushToken(
                user_id=request.user_id,
                push_token=request.push_token,
                device_name=request.device_name
            )
            db.add(new_token)
        
        db.commit()
        return {"status": "success", "message": "Mobile push token registered successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error in mobile subscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not subscribe mobile token")

@router.post("/mobile/unsubscribe")
async def mobile_unsubscribe(request: MobileUnsubscribeRequest, db: Session = Depends(get_db)):
    try:
        db.query(MobilePushToken).filter(MobilePushToken.push_token == request.push_token).delete()
        db.commit()
        return {"status": "success", "message": "Mobile token unsubscribed successfully"}
    except Exception as e:
        db.rollback()
        logger.exception(f"Error in mobile unsubscribe: {e}")
        raise HTTPException(status_code=500, detail="Could not unsubscribe mobile token")
