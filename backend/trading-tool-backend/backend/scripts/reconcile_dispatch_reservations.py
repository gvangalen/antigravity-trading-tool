"""Inspect dispatcher reservations and release only tasks with a terminal result.

Run from the backend directory. Unknown or pending tasks remain reserved and are
reported for operator investigation; this tool never guesses that they are lost.
"""

import argparse
from contextlib import contextmanager
import json
import os
import stat
import subprocess
import time

import redis
from celery import states

from backend.celery_task.celery_app import celery_app
from backend.celery_task.queue_policy import NAMED_QUEUES


def inspect_reservations(client, *, queue_name, app, now=None, stale_seconds=3600):
    now = time.time() if now is None else now
    key = f"dispatcher:{os.getenv('APP_ENV', 'production')}:scheduled:{queue_name}"
    rows = []
    for raw_task_id, created_at in client.zrange(key, 0, -1, withscores=True):
        task_id = raw_task_id.decode() if isinstance(raw_task_id, bytes) else str(raw_task_id)
        state = app.AsyncResult(task_id).state
        rows.append({
            "task_id": task_id,
            "state": state,
            "age_seconds": max(0, int(now - created_at)),
            "stale": created_at <= now - stale_seconds,
            "terminal": state in states.READY_STATES,
        })
    return key, rows


def reconcile(client, *, queue_names, app, apply=False, stale_seconds=3600):
    report = {}
    for queue_name in queue_names:
        key, rows = inspect_reservations(
            client, queue_name=queue_name, app=app, stale_seconds=stale_seconds,
        )
        released = []
        if apply:
            for row in rows:
                if not row["terminal"]:
                    continue
                # Recheck the result immediately before mutation. The exact task ID
                # is the ZSET member, so an unrelated reservation cannot be removed.
                if app.AsyncResult(row["task_id"]).state in states.READY_STATES:
                    if client.zrem(key, row["task_id"]):
                        released.append(row["task_id"])
        report[queue_name] = {
            "reservation_count": len(rows),
            "stale_count": sum(row["stale"] for row in rows),
            "terminal_count": sum(row["terminal"] for row in rows),
            "released_task_ids": released,
            "unresolved_stale_task_ids": [
                row["task_id"] for row in rows if row["stale"] and not row["terminal"]
            ],
        }
    return report


def _contains_task_id(value, task_id):
    """Conservative presence check across Celery's nested inspect payloads."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return task_id in value
    if isinstance(value, dict):
        return any(_contains_task_id(item, task_id) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_task_id(item, task_id) for item in value)
    return False


def verify_lost_task(client, *, app, queue_name, task_id, stale_seconds=3600):
    """Require a fenced, fully stopped single-host Celery fleet."""
    key, rows = inspect_reservations(
        client, queue_name=queue_name, app=app, stale_seconds=stale_seconds,
    )
    row = next((item for item in rows if item["task_id"] == task_id), None)
    if row is None or not row["stale"] or row["terminal"]:
        raise ValueError("Task must have a stale, nonterminal reservation")
    # Early-acknowledged tasks may disappear from both broker structures while
    # executing. A responding replacement worker cannot prove an old worker is
    # gone; require the operator to stop every local Celery process first.
    processes = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    celery_processes = [line for line in processes.splitlines() if "celery" in line.lower()]
    if celery_processes:
        raise ValueError("Celery processes are still running on the fenced host")
    if (app.control.inspect(timeout=10).ping() or {}):
        raise ValueError("Celery workers still respond on this broker")
    if _contains_task_id(client.lrange(queue_name, 0, -1), task_id):
        raise ValueError("Task still appears in the broker queue")
    # Redis transport uses the unacked hash for messages held by workers.
    if _contains_task_id(client.hvals("unacked"), task_id):
        raise ValueError("Task still appears in Redis unacked messages")
    if app.AsyncResult(task_id).state in states.READY_STATES:
        raise ValueError("Task became terminal; use --apply-terminal instead")
    return key, {"task_id": task_id, "queue": queue_name, "age_seconds": row["age_seconds"],
                 "fenced_single_host": True, "result_state": row["state"]}


@contextmanager
def _audit_writer(path):
    if not os.path.isabs(path):
        raise ValueError("Audit log path must be absolute")
    parent = os.path.dirname(path)
    parent_stat = os.stat(parent, follow_symlinks=False)
    if not stat.S_ISDIR(parent_stat.st_mode) or parent_stat.st_uid != os.geteuid() or parent_stat.st_mode & 0o077:
        raise ValueError("Audit directory must be private and owned by this operator")
    new_file = not os.path.lexists(path)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != os.geteuid() or file_stat.st_mode & 0o077:
            raise ValueError("Audit log must be a private regular file")
        if new_file:
            dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        def append(event):
            payload = (json.dumps(event, sort_keys=True) + "\n").encode()
            while payload:
                payload = payload[os.write(fd, payload):]
            os.fsync(fd)
        yield append
    finally:
        os.close(fd)


def release_verified_lost(client, *, app, queue_name, task_id, audit_log, reason,
                          stale_seconds=3600):
    # Repeat control-plane and broker checks after a brief observation interval
    # so a single transient inspect gap cannot authorize release.
    _, first = verify_lost_task(client, app=app, queue_name=queue_name, task_id=task_id,
                                stale_seconds=stale_seconds)
    with _audit_writer(audit_log) as append_audit:
        append_audit({"event": "release_intent", "at": time.time(),
                      "reason": reason, **first})
        time.sleep(5)
        key, evidence = verify_lost_task(client, app=app, queue_name=queue_name,
                                         task_id=task_id, stale_seconds=stale_seconds)
        if not client.zrem(key, task_id):
            raise ValueError("Reservation disappeared during verification")
        append_audit({"event": "release_completed", "at": time.time(),
                      "reason": reason, **evidence})
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", choices=NAMED_QUEUES, action="append")
    parser.add_argument("--stale-seconds", type=int, default=3600)
    parser.add_argument("--apply-terminal", action="store_true")
    parser.add_argument("--release-lost-task-id")
    parser.add_argument("--acknowledge-possible-redelivery", action="store_true")
    parser.add_argument("--fenced-single-host", action="store_true")
    parser.add_argument("--business-effect-verified", action="store_true")
    parser.add_argument("--audit-log")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.stale_seconds < 300:
        parser.error("--stale-seconds must be at least 300")
    if args.release_lost_task_id and (
        not args.queue or len(args.queue) != 1 or
        not args.acknowledge_possible_redelivery or not args.fenced_single_host or
        not args.business_effect_verified or not args.audit_log or not args.reason
    ):
        parser.error("Lost-task release requires one --queue, fenced single host, verified business effect, acknowledgement, private audit log, and reason")
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    client = redis.from_url(broker_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        report = reconcile(
            client,
            queue_names=args.queue or NAMED_QUEUES,
            app=celery_app,
            apply=args.apply_terminal,
            stale_seconds=args.stale_seconds,
        )
        if args.release_lost_task_id:
            report["lost_task_release"] = release_verified_lost(
                client, app=celery_app, queue_name=args.queue[0],
                task_id=args.release_lost_task_id, stale_seconds=args.stale_seconds,
                audit_log=args.audit_log, reason=args.reason,
            )
            report["lost_task_release"]["operator_reason"] = args.reason
    finally:
        client.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if any(
        item["unresolved_stale_task_ids"] for item in report.values()
        if "unresolved_stale_task_ids" in item
    ) and not args.release_lost_task_id else 0


if __name__ == "__main__":
    raise SystemExit(main())
