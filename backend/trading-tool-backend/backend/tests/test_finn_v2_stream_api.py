import asyncio
from types import SimpleNamespace

import pytest

from backend.api import finn_v2_api


class _TrackingSession:
    def __init__(self):
        self.entered = 0
        self.exited = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        self.exited += 1


def _install_envelope_loader(monkeypatch, envelopes):
    session = _TrackingSession()
    remaining = iter(envelopes)

    class _Gateway:
        def __init__(self, _session):
            pass

        async def get_run(self, **_kwargs):
            return SimpleNamespace(id="run-1")

    class _RunService:
        def __init__(self, _session):
            pass

        async def envelope_from_run(self, _run):
            return next(remaining)

    monkeypatch.setattr(finn_v2_api, "async_session_factory", lambda: session)
    monkeypatch.setattr(finn_v2_api, "FinnV2GatewayService", _Gateway)
    monkeypatch.setattr(finn_v2_api, "FinnV2RunService", _RunService)
    return session


def test_finn_v2_stream_closes_session_before_terminal_sse_delivery(monkeypatch):
    """The terminal event must not retain a checked-out request DB connection."""

    envelope = SimpleNamespace(status="completed", dict=lambda: {"run_id": "run-1", "status": "completed"})
    session = _install_envelope_loader(monkeypatch, [envelope])

    class _Request:
        async def is_disconnected(self):
            return False

    monkeypatch.setattr(finn_v2_api, "get_current_user", lambda: {"id": 7})

    async def exercise():
        response = await finn_v2_api.stream_finn_v2_run(
            run_id="run-1",
            raw_request=_Request(),
            current_user={"id": 7},
        )
        events = [event async for event in response.body_iterator]
        return events

    events = asyncio.run(exercise())

    assert events == ['event: run.completed\ndata: {"run_id": "run-1", "status": "completed"}\n\n']
    assert session.entered == session.exited == 1


def test_finn_v2_stream_disconnects_before_opening_a_session(monkeypatch):
    session = _install_envelope_loader(monkeypatch, [])

    class _Request:
        async def is_disconnected(self):
            return True

    async def exercise():
        response = await finn_v2_api.stream_finn_v2_run(
            run_id="run-1",
            raw_request=_Request(),
            current_user={"id": 7},
        )
        return [event async for event in response.body_iterator]

    assert asyncio.run(exercise()) == []
    assert session.entered == session.exited == 0


def test_finn_v2_envelope_loader_closes_session_when_reconstruction_fails(monkeypatch):
    session = _TrackingSession()

    class _Gateway:
        def __init__(self, _session):
            pass

        async def get_run(self, **_kwargs):
            raise RuntimeError("reconstruction failed")

    monkeypatch.setattr(finn_v2_api, "async_session_factory", lambda: session)
    monkeypatch.setattr(finn_v2_api, "FinnV2GatewayService", _Gateway)

    with pytest.raises(RuntimeError, match="reconstruction failed"):
        asyncio.run(finn_v2_api._load_run_envelope(run_id="run-1", user_id=7))

    assert session.entered == session.exited == 1


def test_finn_v2_envelope_loader_closes_session_when_cancelled(monkeypatch):
    session = _TrackingSession()

    class _Gateway:
        def __init__(self, _session):
            pass

        async def get_run(self, **_kwargs):
            raise asyncio.CancelledError()

    monkeypatch.setattr(finn_v2_api, "async_session_factory", lambda: session)
    monkeypatch.setattr(finn_v2_api, "FinnV2GatewayService", _Gateway)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(finn_v2_api._load_run_envelope(run_id="run-1", user_id=7))

    assert session.entered == session.exited == 1


def test_finn_v2_pending_stream_releases_a_session_after_every_poll(monkeypatch):
    pending = SimpleNamespace(status="reasoning", dict=lambda: {"run_id": "run-1", "status": "reasoning"})
    completed = SimpleNamespace(status="completed", dict=lambda: {"run_id": "run-1", "status": "completed"})
    session = _install_envelope_loader(monkeypatch, [pending, pending, completed])

    class _Request:
        async def is_disconnected(self):
            return False

    async def exercise():
        response = await finn_v2_api.stream_finn_v2_run(
            run_id="run-1",
            raw_request=_Request(),
            current_user={"id": 7},
        )
        return [event async for event in response.body_iterator]

    events = asyncio.run(exercise())

    assert [event.split("\n", 1)[0] for event in events] == ["event: run.reasoning", "event: run.completed"]
    assert session.entered == session.exited == 3
