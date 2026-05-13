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

    def send_expo_notification(self, token: str, title: str, body: str, data: Optional[dict] = None, db_session: Optional[Session] = None) -> bool:
        """Sends a single push notification via Expo Push API with robust retries, validation and dead token cleanup."""
        # 1. Validate Token Format
        token_str = str(token).strip()
        if not (token_str.startswith("ExponentPushToken[") or token_str.startswith("ExpoPushToken[")) or not token_str.endswith("]"):
            logger.warning(f"📱 [PushService] Invalid Expo token format detected: '{token_str}'. Skipping dispatch.")
            if db_session:
                self._delete_dead_token(db_session, token_str)
            return False

        payload = {
            "to": token_str,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {}
        }
        url = "https://exp.host/--/api/v2/push/send"
        
        # 2. Retry Loop with Exponential Backoff
        import time
        retries = 3
        backoff_seconds = 1.0
        response = None
        
        for attempt in range(retries):
            try:
                response = httpx.post(url, json=payload, timeout=5.0)
                if response.status_code == 429:
                    logger.warning(f"📱 [PushService] HTTP 429 Rate Limited. Attempt {attempt + 1}/{retries}. Retrying in {backoff_seconds}s...")
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                    continue
                elif response.status_code >= 500:
                    logger.warning(f"📱 [PushService] HTTP {response.status_code} Gateway Error. Attempt {attempt + 1}/{retries}. Retrying in {backoff_seconds}s...")
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                    continue
                break
            except (httpx.NetworkError, httpx.TimeoutException) as net_ex:
                logger.warning(f"📱 [PushService] Network error/timeout: {net_ex}. Attempt {attempt + 1}/{retries}. Retrying in {backoff_seconds}s...")
                if attempt == retries - 1:
                    logger.error("📱 [PushService] Max retries reached on transient network failure.")
                    return False
                time.sleep(backoff_seconds)
                backoff_seconds *= 2

        if not response:
            return False

        # 3. Process Response & Ticket Errors
        if response.status_code == 200:
            resp_json = response.json()
            # Inspect ticket response for DeviceNotRegistered or similar token failures
            data_res = resp_json.get("data")
            
            is_dead = False
            error_message = ""
            
            if isinstance(data_res, dict):
                if data_res.get("status") == "error":
                    error_message = data_res.get("message") or ""
                    details = data_res.get("details") or {}
                    if details.get("error") == "DeviceNotRegistered" or "DeviceNotRegistered" in error_message:
                        is_dead = True
            elif isinstance(data_res, list) and len(data_res) > 0:
                item = data_res[0]
                if item.get("status") == "error":
                    error_message = item.get("message") or ""
                    details = item.get("details") or {}
                    if details.get("error") == "DeviceNotRegistered" or "DeviceNotRegistered" in error_message:
                        is_dead = True

            if is_dead:
                logger.warning(f"🧹 [PushService] Expo reported DeviceNotRegistered for token: {token_str}. Error message: {error_message}")
                if db_session:
                    self._delete_dead_token(db_session, token_str)
                return False

            logger.info(f"📱 Expo push notification successfully sent: {resp_json}")
            return True
        else:
            logger.error(f"📱 Failed to send push via Expo. Status: {response.status_code}, Body: {response.text}")
            return False

    def _delete_dead_token(self, db_session: Session, token_str: str):
        """Helper to cleanly delete a dead mobile token within a safe transaction."""
        try:
            from sqlalchemy import delete
            db_session.execute(delete(MobilePushToken).where(MobilePushToken.push_token == token_str))
            db_session.commit()
            logger.warning(f"🧹 [PushService] Database cleanup: Removed dead mobile push token: {token_str}")
        except Exception as ex:
            logger.error(f"❌ [PushService] Failed to delete dead push token {token_str} from database: {ex}")

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

        # 2. Notify Native Mobile Devices (Expo Push Tokens) with safe DB context passed
        mobile_tokens = db.query(MobilePushToken).filter(MobilePushToken.user_id == user_id).all()
        if mobile_tokens:
            extra_data = {"url": url or "/dashboard"}
            for mob in mobile_tokens:
                if self.send_expo_notification(mob.push_token, title, message, extra_data, db_session=db):
                    success_count += 1
        else:
            logger.info(f"No native mobile push subscriptions found for user {user_id}")

        return success_count

push_service = PushService()
