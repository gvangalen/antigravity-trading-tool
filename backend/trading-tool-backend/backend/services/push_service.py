import json
import os
import httpx
from typing import List, Optional
from pywebpush import webpush, WebPushException
from loguru import logger
from sqlalchemy.orm import Session
from backend.infrastructure.models import PushSubscription, MobilePushToken

class PushService:
    def __init__(self):
        self.public_key = os.getenv("VAPID_PUBLIC_KEY")
        self.private_key = os.getenv("VAPID_PRIVATE_KEY")
        self.email = "mailto:admin@tradamind.com"

    def send_notification(self, subscription: PushSubscription, data: dict):
        """Sends a single web push notification."""
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
            logger.error(f"Web push notification failed: {ex}")
            # If the error is 410 (Gone), the subscription is no longer valid
            if ex.response and ex.response.status_code == 410:
                logger.warning(f"Web subscription expired for endpoint: {subscription.endpoint}")
            return False
        except Exception as ex:
            logger.exception(f"Unexpected error sending web push: {ex}")
            return False

    def send_expo_notification(self, token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
        """Sends a single push notification via Expo Push API."""
        try:
            payload = {
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {}
            }
            url = "https://exp.host/--/api/v2/push/send"
            response = httpx.post(url, json=payload, timeout=5.0)
            if response.status_code == 200:
                resp_json = response.json()
                logger.info(f"📱 Expo push notification successfully sent: {resp_json}")
                return True
            else:
                logger.error(f"📱 Failed to send push via Expo. Status: {response.status_code}, Body: {response.text}")
                return False
        except Exception as e:
            logger.exception(f"Unexpected error in send_expo_notification: {e}")
            return False

    def notify_user(self, db: Session, user_id: int, title: str, message: str, url: Optional[str] = None) -> int:
        """Notifies all active web subscriptions and mobile devices for a user."""
        success_count = 0

        # 1. Notify Web Push Subscriptions
        subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
        if subscriptions:
            payload = {
                "title": title,
                "body": message,
                "icon": "/icons/icon-192x192.png",
                "badge": "/icons/badge-72x72.png",
                "data": {
                    "url": url or "/dashboard"
                }
            }
            for sub in subscriptions:
                if self.send_notification(sub, payload):
                    success_count += 1
        else:
            logger.info(f"No web push subscriptions found for user {user_id}")

        # 2. Notify Native Mobile Devices (Expo Push Tokens)
        mobile_tokens = db.query(MobilePushToken).filter(MobilePushToken.user_id == user_id).all()
        if mobile_tokens:
            extra_data = {"url": url or "/dashboard"}
            for mob in mobile_tokens:
                if self.send_expo_notification(mob.push_token, title, message, extra_data):
                    success_count += 1
        else:
            logger.info(f"No native mobile push subscriptions found for user {user_id}")

        return success_count

push_service = PushService()
