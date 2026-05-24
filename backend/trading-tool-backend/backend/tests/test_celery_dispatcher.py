from backend.celery_task.dispatcher import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_SPREAD_SECONDS,
    _bounded_countdown,
    _dispatch_plan,
)


def test_dispatch_plan_is_bounded_for_10k_users():
    plan = _dispatch_plan(
        10_000,
        batch_size=DEFAULT_BATCH_SIZE,
        max_spread_seconds=DEFAULT_MAX_SPREAD_SECONDS,
    )

    assert plan["batch_size"] == 100
    assert plan["batch_count"] == 100
    assert plan["max_countdown_seconds"] == 300


def test_bounded_countdown_repeats_inside_fixed_window():
    first_batch = [
        _bounded_countdown(i, batch_size=5, max_spread_seconds=20)
        for i in range(5)
    ]
    second_batch = [
        _bounded_countdown(i, batch_size=5, max_spread_seconds=20)
        for i in range(5, 10)
    ]

    assert first_batch == [0, 5, 10, 15, 20]
    assert second_batch == first_batch


def test_bounded_countdown_handles_single_user_and_zero_spread():
    assert _bounded_countdown(0, batch_size=1, max_spread_seconds=300) == 0
    assert _bounded_countdown(500, batch_size=100, max_spread_seconds=0) == 0


def test_dispatch_plan_handles_empty_users():
    plan = _dispatch_plan(0, batch_size=100, max_spread_seconds=300)

    assert plan["batch_count"] == 0
    assert plan["max_countdown_seconds"] == 0
