from __future__ import annotations

from backend.scripts.finn_v2_matrix_transport import observe_terminal


def test_terminal_sse_stops_polling_after_one_persisted_projection_read():
    snapshots = []

    result = observe_terminal(
        remaining_seconds=lambda: 30.0,
        read_sse_terminal=lambda _timeout: ({"status": "completed", "run_id": "run"}, None),
        fetch_persisted_projection=lambda _timeout: (snapshots.append("snapshot") or {"status": "completed", "run_id": "run"}, None),
        initial_projection={"status": "created", "run_id": "run"},
    )

    assert result.used_sse_terminal is True
    assert snapshots == ["snapshot"]
    assert result.terminal == result.sse_terminal


def test_sse_disconnect_uses_bounded_polling_fallback():
    calls = 0

    def fetch(_timeout):
        nonlocal calls
        calls += 1
        return ({"status": "completed", "run_id": "run"} if calls == 2 else {"status": "running", "run_id": "run"}), None

    now = iter((0.0, 0.0, 0.0, 0.1, 0.1, 0.2, 0.2))
    result = observe_terminal(
        remaining_seconds=lambda: 30.0,
        read_sse_terminal=lambda _timeout: ({}, "clienttimeout"),
        fetch_persisted_projection=fetch,
        initial_projection={"status": "created", "run_id": "run"},
        monotonic=lambda: next(now),
        sleep=lambda _seconds: None,
    )

    assert result.used_sse_terminal is False
    assert result.sse_error == "clienttimeout"
    assert result.terminal["status"] == "completed"
    assert calls == 2
