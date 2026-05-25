import json
import os
import httpx
from typing import List, Optional
from pywebpush import webpush, WebPushException
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import PushSubscription, MobilePushToken
from backend.infrastructure.database import async_session_factory

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

    async def send_expo_notification_async(self, token: str, title: str, body: str, data: Optional[dict] = None, db_session: Optional[AsyncSession] = None) -> bool:
        """Sends a single push notification via Expo Push API with robust retries, validation and dead token cleanup."""
        token_str = str(token).strip()
        if not (token_str.startswith("ExponentPushToken[") or token_str.startswith("ExpoPushToken[")) or not token_str.endswith("]"):
            logger.warning(f"📱 [PushService] Invalid Expo token format detected: '{token_str}'. Skipping dispatch.")
            if db_session:
                await self._delete_dead_token_async(db_session, token_str)
            return False

        payload = {
            "to": token_str,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {}
        }
        url = "https://exp.host/--/api/v2/push/send"

        import asyncio
        retries = 3
        backoff_seconds = 1.0
        response = None

        async with httpx.AsyncClient() as client:
            for attempt in range(retries):
                try:
                    response = await client.post(url, json=payload, timeout=5.0)
                    if response.status_code == 429:
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    elif response.status_code >= 500:
                        await asyncio.sleep(backoff_seconds)
                        backoff_seconds *= 2
                        continue
                    break
                except (httpx.NetworkError, httpx.TimeoutException):
                    if attempt == retries - 1:
                        return False
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2

        if not response:
            return False

        if response.status_code == 200:
            resp_json = response.json()
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
                    await self._delete_dead_token_async(db_session, token_str)
                return False

            logger.info(f"📱 Expo push notification successfully sent: {resp_json}")
            return True
        else:
            logger.error(f"📱 Failed to send push via Expo. Status: {response.status_code}, Body: {response.text}")
            return False

    async def _delete_dead_token_async(self, db_session: AsyncSession, token_str: str):
        try:
            await db_session.execute(delete(MobilePushToken).where(MobilePushToken.push_token == token_str))
            await db_session.commit()
            logger.warning(f"🧹 [PushService] Database cleanup: Removed dead mobile push token: {token_str}")
        except Exception as ex:
            logger.error(f"❌ [PushService] Failed to delete dead push token {token_str} from database: {ex}")
            await db_session.rollback()

    async def notify_user_async(self, db: AsyncSession, user_id: int, title: str, message: str, url: Optional[str] = None) -> int:
        """Async version of notify_user for FastAPI AsyncSession."""
        success_count = 0

        res = await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
        subscriptions = res.scalars().all()
        if subscriptions:
            payload = {
                "title": title,
                "body": message,
                "icon": "/icons/icon-192x192.png",
                "badge": "/icons/badge-72x72.png",
                "data": {"url": url or "/dashboard"}
            }
            for sub in subscriptions:
                if self.send_notification(sub, payload):
                    success_count += 1
        
        mob_res = await db.execute(select(MobilePushToken).where(MobilePushToken.user_id == user_id))
        mobile_tokens = mob_res.scalars().all()
        if mobile_tokens:
            extra_data = {"url": url or "/dashboard"}
            for mob in mobile_tokens:
                if await self.send_expo_notification_async(mob.push_token, title, message, extra_data, db_session=db):
                    success_count += 1
        
        return success_count

    def notify_user(self, db, user_id: int, title: str, message: str, url: Optional[str] = None) -> int:
        """Legacy sync bridge. Prefer notify_user_async in new code."""
        import asyncio

        async def _run() -> int:
            async with async_session_factory() as session:
                return await self.notify_user_async(session, user_id, title, message, url)

        return asyncio.run(_run())

push_service = PushService()
