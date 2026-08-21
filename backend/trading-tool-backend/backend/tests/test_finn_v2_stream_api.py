import asyncio
from types import SimpleNamespace

from backend.api import finn_v2_api


def test_finn_v2_stream_generator_waits_without_name_error(monkeypatch):
    """The pending stream must keep polling instead of failing before terminal delivery."""

    run = SimpleNamespace(
        id="run-1",
        status="collecting",
        user_id=7,
    )
    envelope = SimpleNamespace(status="collecting", dict=lambda: {"run_id": "run-1", "status": "collecting"})
    gateway = SimpleNamespace(get_run=lambda **_kwargs: asyncio.sleep(0, result=run))
    run_service = SimpleNamespace(envelope_from_run=lambda _run: asyncio.sleep(0, result=envelope))

    class _Request:
        async def is_disconnected(self):
            return True

    monkeypatch.setattr(finn_v2_api, "get_current_user", lambda: {"id": 7})

    async def exercise():
        response = await finn_v2_api.stream_finn_v2_run(
            run_id="run-1",
            raw_request=_Request(),
            current_user={"id": 7},
            gateway=gateway,
            run_service=run_service,
        )
        events = [event async for event in response.body_iterator]
        return events

    events = asyncio.run(exercise())

    assert events == ['event: run.collecting\ndata: {"run_id": "run-1", "status": "collecting"}\n\n']
