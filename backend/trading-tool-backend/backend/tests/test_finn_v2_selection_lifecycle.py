import asyncio
from time import monotonic

import pytest

from backend.services.finn_v2_responses_loop import FinnResponsesError
from backend.services.finn_v2_run_service import _await_selection_or_lifecycle


def test_provider_failure_before_selection_does_not_wait_for_full_lifecycle_budget():
    async def scenario():
        selection = asyncio.get_running_loop().create_future()

        async def provider_failure():
            await asyncio.sleep(0.01)
            raise FinnResponsesError("responses_provider_timeout")

        lifecycle = asyncio.create_task(provider_failure())
        started = monotonic()
        with pytest.raises(FinnResponsesError, match="responses_provider_timeout"):
            await _await_selection_or_lifecycle(selection, lifecycle, timeout=1)
        assert monotonic() - started < 0.2
        selection.cancel()

    asyncio.run(scenario())


def test_selection_can_continue_while_lifecycle_is_active():
    async def scenario():
        selection = asyncio.get_running_loop().create_future()
        lifecycle = asyncio.create_task(asyncio.sleep(1))
        selection.set_result(None)
        await _await_selection_or_lifecycle(selection, lifecycle, timeout=0.1)
        lifecycle.cancel()
        with pytest.raises(asyncio.CancelledError):
            await lifecycle

    asyncio.run(scenario())
