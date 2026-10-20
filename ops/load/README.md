# Active-user capacity check

Use `active_users.py` against the authorized deployment with one distinct
authenticated fixture account per virtual user. Keep the JSON token file outside
the repo:

```json
[{"user_id": 1, "access_token": "fixture-token"}]
```

Run from the repository root after confirming the deployed SHA and migrations:

```bash
python3 ops/load/active_users.py \
  --base-url https://tradamind.com \
  --fixtures /secure/path/load-fixtures.json \
  --stages 100:120,500:120,1000:300 \
  --allow-production
```

This default profile mixes authenticated workspace, FINN state, and trade-review
reads with ten seconds of average think time. It never submits orders. To include
controlled FINN chat, add `--include-chat --max-chat-requests 50` on fixtures
whose provider budget and data are approved for the test. The script prints only
route-level status counts and latency summaries; it does not print tokens.

Record `/api/system/health` before and after each stage using an operator account.
Compare the Redis cluster metrics, queue depths and age, worker availability,
database connections and slow queries, host CPU and RSS, and provider errors.
Stop escalation when 5xx responses, 429s from normal fixture traffic, growing
queue age, database connection exhaustion, or safety-control errors appear.

The 1000-user claim requires a sustained 1000-user stage with agreed latency and
queue-age thresholds, no unintended trade writes, no cross-account responses,
and independent QA, Security, and Architecture review. This script measures
HTTP behavior; it does not replace the worker-driven FINN release matrix.

Before adding API processes, budget database connections across every API and
Celery process. An API process defaults to at most 15 async plus 3 sync
connections; each worker child defaults to at most 2 async plus 2 sync
connections. Include all worker children and leave headroom for
administration and migrations. Horizontal hosts must share the same PostgreSQL,
Redis rate-limit store, and Celery broker; local Redis on each host cannot provide
clusterwide limits or queues.
