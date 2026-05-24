# Legacy Celery Queue Drain Runbook

This runbook is for draining legacy messages from the default `celery` queue after queue routing has moved to named queues.

## Goal

Drain old misrouted workload from `celery` while preserving real default/fallback work.

Do not aim for `celery = 0`. The goal is that `celery` mostly contains dispatcher/fallback traffic and no longer hides old workload residue.

## Inspect First

Always inspect before applying:

```bash
cd /home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend
python3 backend/scripts/run_legacy_queue_drain_cycle.py \
  --sample-size 100 \
  --max-runs 1 \
  --limit-per-run 100 \
  --min-reroute-ratio 0.6
```

Proceed only when the `operator_summary` shows:

- `reroute_ratio_after >= 0.75`
- `top_tasks_after` are mostly `reroute_to_named_queue`
- `dispatch_for_all_users` is not the dominant task

## Apply Cycle

Use small bounded cycles:

```bash
cd /home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend
python3 backend/scripts/run_legacy_queue_drain_cycle.py \
  --apply \
  --sample-size 100 \
  --max-runs 3 \
  --limit-per-run 500 \
  --max-processed-total 1500 \
  --min-reroute-ratio 0.6 \
  --output-dir ops/queue-drain-artifacts
```

Each run writes a timestamped JSON artifact with the compact `operator_summary`.

## Stop Criteria

Stop draining and reassess when any of these happen:

- `reroute_ratio_after < 0.75`
- `dispatch_for_all_users` becomes dominant in `top_tasks_after`
- `kept` grows materially across cycles
- named queues look unhealthy or are not draining
- the run stops for anything other than `max_processed_total_reached` or `max_runs_reached`

## What To Record

For each cycle, keep the artifact and note:

- artifact path
- `processed`
- `rerouted`
- `kept`
- `reroute_ratio_before`
- `reroute_ratio_after`
- `top_tasks_after`
- default queue `total_depth`

## Current Baseline

Latest confirmed healthy cycle:

- artifact: `ops/queue-drain-artifacts/legacy-queue-drain-celery-apply-20260524T211610Z.json`
- `processed = 1500`
- `rerouted = 1500`
- `kept = 0`
- `reroute_ratio_before = 1.0`
- `reroute_ratio_after = 1.0`
- default queue depth moved from about `83365` to `81859`

This means the visible queue head was still safely rerouteable at that point.
