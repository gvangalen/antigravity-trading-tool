from types import SimpleNamespace
import os
import pytest

from backend.scripts import reconcile_dispatch_reservations as repair


def test_reconcile_only_releases_terminal_tasks(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    class Redis:
        def __init__(self):
            self.members = {"done": 1.0, "retrying": 1.0, "lost": 1.0}

        def zrange(self, key, start, stop, withscores):
            assert key == "dispatcher:staging:scheduled:execution_critical"
            return list(self.members.items())

        def zrem(self, key, member):
            return bool(self.members.pop(member, None) is not None)

    client = Redis()
    app = SimpleNamespace(AsyncResult=lambda task_id: SimpleNamespace(state={
        "done": "SUCCESS", "retrying": "RETRY", "lost": "PENDING",
    }[task_id]))
    result = repair.reconcile(
        client, queue_names=["execution_critical"], app=app,
        apply=True, stale_seconds=3600,
    )
    assert result["execution_critical"]["released_task_ids"] == ["done"]
    assert result["execution_critical"]["unresolved_stale_task_ids"] == ["retrying", "lost"]
    assert set(client.members) == {"retrying", "lost"}


def test_lost_task_release_requires_fenced_absence(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setattr(repair.time, "sleep", lambda _: None)
    monkeypatch.setattr(repair.subprocess, "check_output", lambda *_, **__: "")
    class Redis:
        def __init__(self):
            self.member = {"lost": 1.0}
            self.queued = []

        def zrange(self, *_args, **_kwargs):
            return list(self.member.items())

        def lrange(self, *_args):
            return self.queued

        def hvals(self, *_args):
            return []

        def zrem(self, _key, task_id):
            return bool(self.member.pop(task_id, None))

    class Inspect:
        def ping(self):
            return {}

    client = Redis()
    app = SimpleNamespace(
        AsyncResult=lambda _: SimpleNamespace(state="PENDING"),
        control=SimpleNamespace(inspect=lambda **_: Inspect()),
    )
    client.queued = [b'{"headers":{"id":"lost"}}']
    audit_log = str(tmp_path / "repair.jsonl")
    try:
        repair.release_verified_lost(client, app=app, queue_name="execution_critical", task_id="lost",
                                     audit_log=audit_log, reason="verified business outcome")
        assert False, "broker-present task should block release"
    except ValueError as exc:
        assert "broker queue" in str(exc)
    assert "lost" in client.member
    client.queued = []
    monkeypatch.setattr(repair.subprocess, "check_output", lambda *_, **__: "22 celery worker")
    try:
        repair.verify_lost_task(client, app=app, queue_name="execution_critical", task_id="lost")
        assert False, "running worker should block release"
    except ValueError as exc:
        assert "still running" in str(exc)
    monkeypatch.setattr(repair.subprocess, "check_output", lambda *_, **__: "")
    evidence = repair.release_verified_lost(client, app=app, queue_name="execution_critical", task_id="lost",
                                            audit_log=audit_log, reason="verified business outcome")
    assert evidence["task_id"] == "lost"
    assert "lost" not in client.member
    assert '"event": "release_intent"' in (tmp_path / "repair.jsonl").read_text()
    assert '"event": "release_completed"' in (tmp_path / "repair.jsonl").read_text()


def test_audit_writer_refuses_public_directory(tmp_path):
    os.chmod(tmp_path, 0o755)
    with pytest.raises(ValueError, match="Audit directory"):
        with repair._audit_writer(str(tmp_path / "repair.jsonl")):
            pass
