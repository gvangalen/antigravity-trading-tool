from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from backend.celery_task.queue_policy import DEFAULT_QUEUE, DISPATCHER_TASK_NAME, resolve_task_queue


@dataclass(frozen=True)
class LegacyQueueDecision:
    task_name: Optional[str]
    target_queue: str
    reroute: bool
    reason: str


def _decode_message(raw_message: Any) -> Optional[Dict[str, Any]]:
    if raw_message is None:
        return None
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    if not isinstance(raw_message, str):
        return None
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def extract_task_name(raw_message: Any) -> Optional[str]:
    payload = _decode_message(raw_message)
    if not payload:
        return None
    headers = payload.get("headers")
    if not isinstance(headers, dict):
        return None
    task_name = headers.get("task")
    return task_name if isinstance(task_name, str) else None


def classify_legacy_queue_message(
    raw_message: Any,
    *,
    source_queue: str = DEFAULT_QUEUE,
) -> LegacyQueueDecision:
    task_name = extract_task_name(raw_message)
    if not task_name:
        return LegacyQueueDecision(
            task_name=None,
            target_queue=source_queue,
            reroute=False,
            reason="missing_task_header",
        )

    target_queue = resolve_task_queue(task_name)
    if task_name == DISPATCHER_TASK_NAME:
        return LegacyQueueDecision(
            task_name=task_name,
            target_queue=source_queue,
            reroute=False,
            reason="dispatcher_stays_on_default",
        )

    if target_queue == source_queue:
        return LegacyQueueDecision(
            task_name=task_name,
            target_queue=source_queue,
            reroute=False,
            reason="default_queue_policy",
        )

    return LegacyQueueDecision(
        task_name=task_name,
        target_queue=target_queue,
        reroute=True,
        reason="reroute_to_named_queue",
    )


def summarize_legacy_queue_messages(
    raw_messages: Iterable[Any],
    *,
    source_queue: str = DEFAULT_QUEUE,
    limit: int = 10,
) -> Dict[str, Any]:
    decisions = [
        classify_legacy_queue_message(raw_message, source_queue=source_queue)
        for raw_message in raw_messages
    ]
    task_counts: Counter[tuple[Optional[str], str, bool, str]] = Counter(
        (decision.task_name, decision.target_queue, decision.reroute, decision.reason)
        for decision in decisions
    )
    top_tasks: List[Dict[str, Any]] = []
    for (task_name, target_queue, reroute, reason), count in task_counts.most_common(limit):
        top_tasks.append({
            "task_name": task_name,
            "target_queue": target_queue,
            "reroute": reroute,
            "reason": reason,
            "count": count,
        })

    return {
        "sample_size": len(decisions),
        "rerouteable_count": sum(1 for decision in decisions if decision.reroute),
        "kept_on_default_count": sum(1 for decision in decisions if not decision.reroute),
        "top_tasks": top_tasks,
    }
