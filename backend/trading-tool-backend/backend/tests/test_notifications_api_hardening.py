from pathlib import Path


NOTIFICATIONS_API = (
    Path(__file__).resolve().parents[1]
    / "api"
    / "notifications_api.py"
)


def _source() -> str:
    return NOTIFICATIONS_API.read_text(encoding="utf-8")


def test_notifications_api_uses_async_session_not_sync_query():
    source = _source()

    assert "AsyncSession" in source
    assert "sqlalchemy.orm import Session" not in source
    assert ".query(" not in source
    assert "await db.execute(" in source


def test_notifications_api_uses_authenticated_user_context():
    source = _source()

    assert "Depends(get_current_user)" in source
    assert 'user_id = int(current_user["id"])' in source
    assert "request.user_id" not in source


def test_notifications_unsubscribe_is_user_scoped():
    source = _source()

    assert "PushSubscription.user_id == user_id" in source
    assert "MobilePushToken.user_id == user_id" in source
