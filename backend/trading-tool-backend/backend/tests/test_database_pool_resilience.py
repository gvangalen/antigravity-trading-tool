from backend.infrastructure.database import engine


def test_async_database_pool_replaces_idle_connections_before_visible_work():
    pool = engine.sync_engine.pool

    assert pool._pre_ping is True
    assert pool._recycle == 60
    assert pool._timeout == 3
