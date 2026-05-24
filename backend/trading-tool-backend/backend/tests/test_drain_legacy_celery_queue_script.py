from backend.scripts import drain_legacy_celery_queue as drain_script


class _FakeRedisClient:
    def __init__(self):
        self.queues = {
            "celery": [
                b'{"headers":{"task":"backend.celery_task.dispatcher.dispatch_for_all_users"}}',
                b'{"headers":{"task":"backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores"}}',
                b'{"headers":{"task":"backend.celery_task.technical_task.fetch_technical_data_day"}}',
            ],
            "market_data": [],
            "scoring": [],
            "portfolio": [],
            "ai_generation": [],
            "execution_critical": [],
        }

    def llen(self, queue_name):
        return len(self.queues.get(queue_name, []))

    def lrange(self, queue_name, start, end):
        items = list(self.queues.get(queue_name, []))
        if start < 0:
            start = max(0, len(items) + start)
        if end < 0:
            end = len(items) + end
        return items[start : end + 1]

    def rpop(self, queue_name):
        items = self.queues.get(queue_name, [])
        if not items:
            return None
        return items.pop()

    def lpush(self, queue_name, value):
        self.queues.setdefault(queue_name, []).insert(0, value)

    def lpop(self, queue_name):
        items = self.queues.get(queue_name, [])
        if not items:
            return None
        return items.pop(0)

    def rpush(self, queue_name, value):
        self.queues.setdefault(queue_name, []).append(value)

    def delete(self, queue_name):
        self.queues.pop(queue_name, None)

    def close(self):
        return None


def test_drain_legacy_queue_reports_before_and_after_depths(monkeypatch):
    client = _FakeRedisClient()
    monkeypatch.setattr(drain_script, "_broker_client", lambda: client)

    result = drain_script.drain_legacy_queue("celery", 10, runtime_cap_seconds=15.0)

    assert result["processed"] == 3
    assert result["rerouted"] == 2
    assert result["kept"] == 1
    assert result["before_queue_depths"]["celery"] == 3
    assert result["after_queue_depths"]["celery"] == 1
    assert result["after_queue_depths"]["scoring"] == 1
    assert result["after_queue_depths"]["market_data"] == 1
    assert result["stop_reason"] == "queue_drained"
    assert result["runtime_cap_seconds"] == 15.0


def test_drain_legacy_queue_stops_on_runtime_cap(monkeypatch):
    client = _FakeRedisClient()
    monkeypatch.setattr(drain_script, "_broker_client", lambda: client)

    timestamps = iter([0.0, 0.0, 20.0, 20.0])
    monkeypatch.setattr(drain_script.time, "monotonic", lambda: next(timestamps))

    result = drain_script.drain_legacy_queue("celery", 10, runtime_cap_seconds=5.0)

    assert result["processed"] == 1
    assert result["stop_reason"] == "runtime_cap_reached"
    assert result["after_queue_depths"]["celery"] == 2
