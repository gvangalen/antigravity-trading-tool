from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PUSH_SERVICE = BACKEND_ROOT / "services" / "push_service.py"


def _source() -> str:
    return PUSH_SERVICE.read_text(encoding="utf-8")


def test_push_service_uses_async_sqlalchemy_boundary():
    source = _source()

    assert "sqlalchemy.orm import Session" not in source
    assert ".query(" not in source
    assert "from sqlalchemy.ext.asyncio import AsyncSession" in source
    assert "select(PushSubscription).where(PushSubscription.user_id == user_id)" in source
    assert "select(MobilePushToken).where(MobilePushToken.user_id == user_id)" in source


def test_push_service_legacy_notify_user_is_bridge_only():
    source = _source()

    bridge_start = source.index("def notify_user(")
    bridge_source = source[bridge_start:]

    assert "Legacy sync bridge" in bridge_source
    assert "async_session_factory" in bridge_source
    assert "notify_user_async(session, user_id, title, message, url)" in bridge_source
    assert "db.query" not in bridge_source


def test_push_service_dead_token_cleanup_is_async():
    source = _source()

    assert "async def _delete_dead_token_async" in source
    assert "await db_session.execute(delete(MobilePushToken)" in source
    assert "await db_session.commit()" in source
