import json
import os
from typing import List, Optional
from pywebpush import webpush, WebPushException
from loguru import logger
from sqlalchemy.orm import Session
from backend.infrastructure.models import PushSubscription

class PushService:
    def __init__(self):
        self.public_key = os.getenv("VAPID_PUBLIC_KEY")
        self.private_key = os.getenv("VAPID_PRIVATE_KEY")
        self.email = "mailto:admin@tradamind.com"

    def send_notification(self, subscription: PushSubscription, data: dict):
        """Sends a single push notification."""
        if not self.public_key or not self.private_key:
            logger.error("VAPID keys not configured in environment")
            return False

        try:
            subscription_info = {
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth
                }
            }
            
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(data),
                vapid_private_key=self.private_key,
                vapid_claims={"sub": self.email}
            )
            return True
        except WebPushException as ex:
            logger.error(f"Push notification failed: {ex}")
            # If the error is 410 (Gone), the subscription is no longer valid
            if ex.response and ex.response.status_code == 410:
                logger.warning(f"Subscription expired for endpoint: {subscription.endpoint}")
            return False
        except Exception as ex:
            logger.exception(f"Unexpected error sending push: {ex}")
            return False

    def notify_user(self, db: Session, user_id: int, title: str, message: str, url: Optional[str] = None):
        """Notifies all active subscriptions for a user."""
        subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
        
        if not subscriptions:
            logger.info(f"No push subscriptions found for user {user_id}")
            return 0

        payload = {
            "title": title,
            "body": message,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/badge-72x72.png",
            "data": {
                "url": url or "/dashboard"
            }
        }

        success_count = 0
        for sub in subscriptions:
            if self.send_notification(sub, payload):
                success_count += 1
        
        return success_count

push_service = PushService()
