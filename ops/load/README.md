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

This default profile mixes authenticated workspace, FINN conversation, and trade-review
reads with ten seconds of average think time. It never submits orders. To include
controlled FINN chat, use separately approved accounts and add
`--include-chat --max-chat-requests 50`; the provisioned capacity fixture tokens
are restricted to three read routes and return 403 for chat. The script prints only
route-level status counts and latency summaries; it does not print tokens.

## Prepare distinct fixture accounts

`backend/scripts/provision_capacity_fixtures.py` creates at most 1000 marked
accounts in the selected database. Run it from `backend/trading-tool-backend`
with the target database and JWT environment loaded and `PYTHONPATH=.`. It
requires the expected database host, port and name on every command. Production
requires `--allow-production`; mutating actions also require `--apply`. First
inspect the campaign with `plan`, then run `create` and `issue` in the approved
test window. The token output must be an absolute path outside the repo under
a preexisting private (0700) directory. The script creates a 0600 JSON file
and never prints tokens.

```bash
python -m backend.scripts.provision_capacity_fixtures plan \
  --campaign capacity-oct20 --count 1000 \
  --expected-db-host "$DB_HOST" --expected-db-port "$DB_PORT" \
  --expected-db-name "$DB_NAME" \
  --allow-production
python -m backend.scripts.provision_capacity_fixtures create \
  --campaign capacity-oct20 --count 1000 \
  --expected-db-host "$DB_HOST" --expected-db-port "$DB_PORT" \
  --expected-db-name "$DB_NAME" \
  --allow-production --apply
python -m backend.scripts.provision_capacity_fixtures issue \
  --campaign capacity-oct20 --count 1000 \
  --expected-db-host "$DB_HOST" --expected-db-port "$DB_PORT" \
  --expected-db-name "$DB_NAME" \
  --output /secure/private-directory/capacity-fixtures.json \
  --allow-production --apply
```

After the test, use `deactivate` with the same campaign/count/target flags and
`--allow-production --apply`, then delete the token file. Tokens are stateless:
already issued tokens can still access the three read routes until expiry
(20 minutes by default, at most 60). Use a new campaign for every run; never
reuse a deactivated campaign.

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
