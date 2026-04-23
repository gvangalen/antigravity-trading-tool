from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.infrastructure.database import get_db
from backend.infrastructure.models import PushSubscription, User
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
