from backend.services import cluster_metrics


def test_cluster_metrics_rolls_up_two_processes_in_same_minute(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(cluster_metrics.time, "time", lambda: 120.0)

    class Pipeline:
        def __init__(self, values):
            self.values = values
            self.commands = []

        def hincrby(self, key, field, amount):
            self.commands.append(("increment", key, field, amount))
            return self

        def expire(self, key, seconds):
            self.commands.append(("expire", key, seconds))
            return self

        def hgetall(self, key):
            self.commands.append(("read", key))
            return self

        def execute(self):
            if self.commands[0][0] == "read":
                return [self.values.get(command[1], {}) for command in self.commands]
            for command in self.commands:
                if command[0] == "increment":
                    _, key, field, amount = command
                    row = self.values.setdefault(key, {})
                    row[field] = row.get(field, 0) + amount
            return []

    class Redis:
        def __init__(self):
            self.values = {}

        def pipeline(self, transaction=False):
            assert transaction is False
            return Pipeline(self.values)

    monkeypatch.setattr(cluster_metrics, "_client", Redis())
    cluster_metrics.record_counter("retry", "bot", 1)
    cluster_metrics.record_counter("retry", "bot", 2)
    cluster_metrics.record_latency("dashboard", 80)
    cluster_metrics.record_latency("dashboard", 300)

    result = cluster_metrics.snapshot()
    assert result["ready"] is True
    assert result["counters"]["retry:bot"] == 3
    assert result["latency_histograms"]["dashboard"] == {
        "samples": 2, "p50_upper_ms": 100, "p95_upper_ms": 500,
    }
