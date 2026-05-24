from backend.celery_task.legacy_queue_drain import (
    classify_legacy_queue_message,
    extract_task_name,
    summarize_legacy_queue_messages,
)


def _message(task_name: str, kwargsrepr: str = "{}") -> str:
    return (
        '{"body":"W1tdLCB7fSwge31d","content-encoding":"utf-8","content-type":"application/json",'
        f'"headers":{{"task":"{task_name}","kwargsrepr":"{kwargsrepr}"}},"properties":{{}}}}'
    )


def test_extract_task_name_from_raw_redis_message():
    raw = _message("backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores")

    task_name = extract_task_name(raw)

    assert task_name == "backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores"


def test_classify_legacy_queue_message_reroutes_named_task():
    raw = _message("backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores")

    decision = classify_legacy_queue_message(raw)

    assert decision.reroute is True
    assert decision.target_queue == "scoring"
    assert decision.reason == "reroute_to_named_queue"


def test_classify_legacy_queue_message_keeps_dispatcher_on_default():
    raw = _message(
        "backend.celery_task.dispatcher.dispatch_for_all_users",
        "{'task_name': 'backend.celery_task.setup_task.run_setup_agent_daily'}",
    )

    decision = classify_legacy_queue_message(raw)

    assert decision.reroute is False
    assert decision.target_queue == "celery"
    assert decision.reason == "dispatcher_stays_on_default"


def test_summarize_legacy_queue_messages_counts_rerouteable_and_kept():
    summary = summarize_legacy_queue_messages([
        _message("backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores"),
        _message("backend.celery_task.dispatcher.dispatch_for_all_users"),
        '{"headers":{}}',
    ])

    assert summary["sample_size"] == 3
    assert summary["rerouteable_count"] == 1
    assert summary["kept_on_default_count"] == 2
    assert summary["top_tasks"][0]["count"] >= 1
