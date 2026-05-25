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
- `/api/system/health` `queue_metrics.<queue>.depth`
- `/api/system/health` `queue_metrics.<queue>.timestamped_sample_size`
- `/api/system/health` `queue_metrics.<queue>.oldest_message_age_seconds`
- `/api/system/health` `queue_metrics.<queue>.estimated_drain_per_minute`

## Queue Age And Throughput Notes

New Celery tasks are stamped with a `published_at` header before they enter Redis. Deep health uses that header to report queue age for sampled messages.

Older legacy messages often do not have a timestamp. In that case deep health reports:

- `timestamped_sample_size = 0`
- `oldest_message_age_seconds = null`
- `age_source = unavailable`

That is expected. Do not infer freshness for unstamped legacy messages.

`estimated_drain_per_minute` is a trend signal based on the previous `/api/system/health` call served by the same backend process. It is useful for operator comparisons during drain work, but it is not a durable Celery event counter.

## Current Baseline

Latest controlled apply cycle:

- artifact: `ops/queue-drain-artifacts/legacy-queue-drain-celery-apply-20260525T064122Z.json`
- `processed = 9000`
- `rerouted = 8782`
- `kept = 218`
- `reroute_ratio_before = 0.97`
- `reroute_ratio_after = 0.695`
- `stop_reason = reroute_ratio_below_threshold`
- default queue depth moved from about `67830` to `59034` during the run

This was a successful controlled drain, and it stopped for the intended safety reason. After the run, named queues were materially fuller, so do not immediately keep draining just because the default queue still has depth.

Latest post-run health showed:

- `celery` depth about `59012`
- `celery` sample reroute ratio about `0.8`
- `scoring`, `portfolio`, `ai_generation`, and `execution_critical` queues materially increased because legacy work was moved to the correct lanes
- market snapshot was temporarily `stale`

Recommended next drain operation:

- wait until named queues visibly drain and market snapshot health is `ok`
- inspect first with `--sample-size 200`
- apply again only if `reroute_ratio_after >= 0.75` and dispatcher/default work is not dominant
