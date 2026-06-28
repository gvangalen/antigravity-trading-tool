import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

from backend.services.auth_service import AuthService


class _FakeRepo:
    def __init__(self):
        self.users_by_email = {}
        self.users_by_id = {}
        self.refresh_sessions = {}
        self.refresh_by_hash = {}
        self.password_reset_tokens = {}
        self.last_login_updates = []

    async def get_by_email(self, email):
        return self.users_by_email.get(email)

    async def get_by_id(self, user_id):
        return self.users_by_id.get(user_id)

    async def count_users(self):
        return len(self.users_by_id)

    async def create_user(self, **kwargs):
        user = SimpleNamespace(id=len(self.users_by_id) + 1, is_active=True, ai_plan="basis", ai_requests_limit_day=25, ai_requests_used_day=0, **kwargs)
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        return user

    async def update_last_login(self, user_id, login_time):
        self.last_login_updates.append((user_id, login_time))

    async def create_refresh_session(self, user_id, jti, token_hash, expires_at):
        session = SimpleNamespace(
            user_id=user_id,
            jti=jti,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
            rotated_at=None,
            revoked_reason=None,
            replaced_by_jti=None,
            last_used_at=None,
        )
        self.refresh_sessions[jti] = session
        self.refresh_by_hash[token_hash] = session
        return session

    async def get_refresh_session(self, jti):
        return self.refresh_sessions.get(jti)

    async def rotate_refresh_session(self, current_session, *, replaced_by_jti, rotated_at):
        current_session.rotated_at = rotated_at
        current_session.revoked_at = rotated_at
        current_session.revoked_reason = "rotated"
        current_session.replaced_by_jti = replaced_by_jti
        current_session.last_used_at = rotated_at

    async def revoke_refresh_session(self, current_session, *, reason, revoked_at):
        current_session.revoked_at = revoked_at
        current_session.revoked_reason = reason
        current_session.last_used_at = revoked_at

    async def revoke_all_refresh_sessions_for_user(self, user_id, *, reason, revoked_at):
        for session in self.refresh_sessions.values():
            if session.user_id == user_id and session.revoked_at is None:
                session.revoked_at = revoked_at
                session.revoked_reason = reason
                session.last_used_at = revoked_at

    async def update_password_hash(self, user_id, password_hash):
        user = self.users_by_id.get(user_id)
        if not user:
            return None
        user.password_hash = password_hash
        return user

    async def create_password_reset_token(self, *, user_id, token_hash, expires_at, locale=None):
        token = SimpleNamespace(
            id=len(self.password_reset_tokens) + 1,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            locale=locale,
            created_at=datetime.now(timezone.utc),
            used_at=None,
            revoked_at=None,
            revoked_reason=None,
        )
        self.password_reset_tokens[token_hash] = token
        return token

    async def get_password_reset_token(self, token_hash):
        return self.password_reset_tokens.get(token_hash)

    async def revoke_password_reset_tokens_for_user(self, user_id, *, reason, revoked_at, exclude_token_id=None):
        for token in self.password_reset_tokens.values():
            if token.user_id != user_id:
                continue
            if exclude_token_id is not None and token.id == exclude_token_id:
                continue
            if token.used_at is None and token.revoked_at is None:
                token.revoked_at = revoked_at
                token.revoked_reason = reason

    async def consume_password_reset_token(self, token, *, used_at):
        token.used_at = used_at
        token.revoked_reason = "used"


def _user(user_id=7, email="henk@example.com", password_hash="hashed-password", role="user"):
    return SimpleNamespace(
        id=user_id,
        email=email,
        password_hash=password_hash,
        role=role,
        is_active=True,
        first_name="Henk",
        last_name="QA",
        ai_plan="basis",
        ai_requests_limit_day=25,
        ai_requests_used_day=0,
        ai_preferences={},
    )


def test_login_creates_persisted_refresh_session(monkeypatch):
    from backend.services import auth_service as auth_service_module

    repo = _FakeRepo()
    user = _user()
    repo.users_by_email[user.email] = user
    repo.users_by_id[user.id] = user

    monkeypatch.setattr(auth_service_module, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(auth_service_module, "create_access_token", lambda payload: f"access:{payload['sub']}")
    monkeypatch.setattr(auth_service_module, "create_refresh_token", lambda payload: f"refresh:{payload['jti']}")
    monkeypatch.setattr(auth_service_module, "hash_token", lambda token: f"hash:{token}")

    service = AuthService(repo)
    result = asyncio.run(service.login_user(SimpleNamespace(email=user.email, password="test123")))

    assert result["access_token"] == f"access:{user.id}"
    assert result["refresh_token"].startswith("refresh:")
    refresh_jti = result["refresh_token"].split("refresh:", 1)[1]
    stored = repo.refresh_sessions[refresh_jti]
    assert stored.user_id == user.id
    assert stored.token_hash == f"hash:{result['refresh_token']}"
    assert stored.expires_at.tzinfo is None
    assert repo.last_login_updates and repo.last_login_updates[0][0] == user.id


def test_refresh_rotates_session_and_issues_new_tokens(monkeypatch):
    from backend.services import auth_service as auth_service_module

    repo = _FakeRepo()
    user = _user()
    repo.users_by_id[user.id] = user
    old_session = asyncio.run(repo.create_refresh_session(
        user_id=user.id,
        jti="old-jti",
        token_hash="hash:refresh:old-jti",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    ))

    monkeypatch.setattr(
        auth_service_module,
        "decode_token",
        lambda token, verify_exp=True: {"sub": str(user.id), "type": "refresh", "jti": "old-jti"},
    )
    monkeypatch.setattr(auth_service_module, "hash_token", lambda token: f"hash:{token}")
    monkeypatch.setattr(auth_service_module, "create_access_token", lambda payload: f"access:{payload['sub']}")
    monkeypatch.setattr(auth_service_module, "create_refresh_token", lambda payload: f"refresh:{payload['jti']}")

    service = AuthService(repo)
    result = asyncio.run(service.refresh_access_token("refresh:old-jti"))

    assert result["access_token"] == f"access:{user.id}"
    assert result["refresh_token"].startswith("refresh:")
    assert old_session.revoked_reason == "rotated"
    assert old_session.replaced_by_jti is not None
    assert old_session.replaced_by_jti in repo.refresh_sessions


def test_refresh_rejects_revoked_session(monkeypatch):
    from backend.services import auth_service as auth_service_module

    repo = _FakeRepo()
    user = _user()
    repo.users_by_id[user.id] = user
    session = asyncio.run(repo.create_refresh_session(
        user_id=user.id,
        jti="revoked-jti",
        token_hash="hash:refresh:revoked-jti",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    ))
    session.revoked_at = datetime.now(timezone.utc)
    session.revoked_reason = "logout"

    monkeypatch.setattr(
        auth_service_module,
        "decode_token",
        lambda token, verify_exp=True: {"sub": str(user.id), "type": "refresh", "jti": "revoked-jti"},
    )
    monkeypatch.setattr(auth_service_module, "hash_token", lambda token: f"hash:{token}")

    service = AuthService(repo)

    try:
        asyncio.run(service.refresh_access_token("refresh:revoked-jti"))
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_logout_revokes_current_refresh_session(monkeypatch):
    from backend.services import auth_service as auth_service_module

    repo = _FakeRepo()
    session = asyncio.run(repo.create_refresh_session(
        user_id=7,
        jti="logout-jti",
        token_hash="hash:refresh:logout-jti",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    ))

    monkeypatch.setattr(
        auth_service_module,
        "decode_token",
        lambda token, verify_exp=False: {"sub": "7", "type": "refresh", "jti": "logout-jti"},
    )
    monkeypatch.setattr(auth_service_module, "hash_token", lambda token: f"hash:{token}")

    service = AuthService(repo)
    revoked = asyncio.run(service.revoke_refresh_token("refresh:logout-jti"))

    assert revoked is True
    assert session.revoked_reason == "logout"
    assert session.revoked_at is not None
    assert session.revoked_at.tzinfo is None


def test_refresh_session_timestamps_are_db_safe_naive_utc():
    now = AuthService._db_utc_now()
    expiry = AuthService._refresh_expiry()

    assert now.tzinfo is None
    assert expiry.tzinfo is None
    assert expiry > now


def test_refresh_migration_exists():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrations"
        / "2026_05_26_auth_refresh_sessions.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS auth_refresh_sessions" in source
    assert "jti VARCHAR NOT NULL UNIQUE" in source
    assert "token_hash VARCHAR NOT NULL UNIQUE" in source


def test_password_reset_request_creates_single_use_token_and_sends_localized_email(monkeypatch):
    from backend.services import auth_service as auth_service_module

    repo = _FakeRepo()
    user = _user()
    repo.users_by_email[user.email] = user
    repo.users_by_id[user.id] = user
    sent = {}

    monkeypatch.setattr(auth_service_module, "hash_token", lambda token: f"hash:{token}")
    monkeypatch.setattr(auth_service_module.secrets, "token_urlsafe", lambda _: "reset-token")
    monkeypatch.setattr(
        auth_service_module,
        "send_email",
        lambda subject, body, receiver: sent.update(
            {"subject": subject, "body": body, "receiver": receiver}
        ),
    )

    service = AuthService(repo)
    asyncio.run(service.request_password_reset(SimpleNamespace(email=user.email, locale="en")))

    stored = repo.password_reset_tokens["hash:reset-token"]
    assert stored.user_id == user.id
    assert stored.locale == "en"
    assert sent["receiver"] == user.email
    assert "Reset your Tradamind password" == sent["subject"]
    assert "/reset-password?token=reset-token" in sent["body"]


def test_password_reset_validation_rejects_used_or_expired_tokens(monkeypatch):
    repo = _FakeRepo()
    user = _user()
    repo.users_by_id[user.id] = user
    token = asyncio.run(
        repo.create_password_reset_token(
            user_id=user.id,
            token_hash="hash:reset-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            locale="nl",
        )
    )

    from backend.services import auth_service as auth_service_module

    monkeypatch.setattr(auth_service_module, "hash_token", lambda raw: f"hash:{raw}")
    service = AuthService(repo)
    assert asyncio.run(service.validate_password_reset_token("reset-token")) is False

    token.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    token.used_at = datetime.now(timezone.utc)
    assert asyncio.run(service.validate_password_reset_token("reset-token")) is False


def test_password_reset_updates_password_and_revokes_other_sessions(monkeypatch):
    from backend.services import auth_service as auth_service_module

    repo = _FakeRepo()
    user = _user(password_hash="old-hash")
    repo.users_by_id[user.id] = user
    repo.users_by_email[user.email] = user
    asyncio.run(
        repo.create_refresh_session(
            user_id=user.id,
            jti="jti-1",
            token_hash="hash:refresh:jti-1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    token = asyncio.run(
        repo.create_password_reset_token(
            user_id=user.id,
            token_hash="hash:reset-token",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            locale="nl",
        )
    )
    asyncio.run(
        repo.create_password_reset_token(
            user_id=user.id,
            token_hash="hash:other-token",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            locale="nl",
        )
    )

    monkeypatch.setattr(auth_service_module, "hash_token", lambda raw: f"hash:{raw}")
    monkeypatch.setattr(auth_service_module, "hash_password", lambda raw: f"hashed:{raw}")

    service = AuthService(repo)
    asyncio.run(service.reset_password(SimpleNamespace(token="reset-token", password="new-password-1")))

    assert user.password_hash == "hashed:new-password-1"
    assert repo.refresh_sessions["jti-1"].revoked_reason == "password_reset"
    assert token.used_at is not None
    assert token.revoked_reason == "used"
    assert repo.password_reset_tokens["hash:other-token"].revoked_reason == "password_reset"


def test_password_reset_migration_exists():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrations"
        / "2026_06_28_auth_password_reset_tokens.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS auth_password_reset_tokens" in source
    assert "token_hash VARCHAR NOT NULL UNIQUE" in source
    assert "used_at TIMESTAMPTZ" in source
