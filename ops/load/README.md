# Active-user capacity check

Use `active_users.py` against the authorized deployment with one distinct
authenticated fixture account per virtual user. Keep the JSON token file outside
the repo:

```json
[{"user_id": 1, "email": "capacity+example-0001@load.example", "access_token": "fixture-token"}]
```

Run from the repository root after confirming the deployed SHA and migrations:

```bash
python3 ops/load/active_users.py \
  --base-url https://tradamind.com \
  --fixtures /secure/path/load-fixtures.json \
  --stages 100:120,500:120,1000:300 \
  --max-workspace-p95-ms 2000 --max-finn-p95-ms 1000 \
  --max-reviews-p95-ms 1000 --between-stage-pause-seconds 60 \
  --allow-production
```

For a 1000-user run, start the generator from a shell with `ulimit -n 4096`
or a higher available soft limit. The harness rejects a production run when
the soft file-descriptor limit is below the requested user count plus 128.
It prints the effective limit, event-loop lag, generator CPU percentage and
maximum open descriptors. Every synthetic request sends a unique `cap-` trace
ID. The five slowest requests per route include UTC start/end epoch seconds,
client duration, app duration and trace ID, without tokens or response bodies.

To locate latency outside the app, install `nginx_capacity_timing.conf` once
in the production Nginx `http` context and add the following directive to the
actual `tradamind.com` `/api/` location for the bounded run. First inspect
`nginx -T` and copy every effective standard `access_log` directive, including
its path, format and options, into that location. Defining a log inside a
location replaces inherited access logs. The current production config was
observed using `/var/log/nginx/access.log`, so its example is:

```nginx
access_log /var/log/nginx/access.log;
access_log /var/log/nginx/capacity_timing.log capacity_timing if=$capacity_trace;
```

Validate the rendered config with `nginx -t` before reloading, and confirm
normal API requests still reach the standard log. The dedicated log records
requests bearing a matching `cap-` trace header; that header is not proof of
fixture identity. It contains no Authorization header, query string or
response body. Restrict access to the dedicated file, monitor its size during
the bounded run, and remove the temporary logging after diagnosis.
For the same trace ID, Nginx request start is approximately
`end_utc_epoch - request_s`; compare that with the harness request start to
separate delay before Nginx from proxy/upstream delay. Compare
`upstream_connect_s`, `upstream_header_s`, `upstream_response_s` and app time
to locate the remaining wait. The operator should also sample generator FD
and socket counts and host CPU during the stage.

The harness accepts the exact production origin `https://tradamind.com` with
`--allow-production`, or a loopback origin for local checks. Before each stage
it verifies `/api/auth/me` returns the expected account ID and email for every
fixture. The default profile mixes authenticated workspace, FINN conversation,
and trade-review reads with ten seconds of average think time. Each fixture's
first request is spread deterministically across that think-time window, so
the stage measures concurrently active users without a synchronized login
burst. The configured stage duration starts after this ramp, so `1000:300`
allows 300 seconds with all fixtures active after the ten-second ramp. It stops before
the next stage on any non-2xx response or timeout and reports successful and
all-response p95 separately. Production runs require explicit p95 limits for all three routes and at least
30 seconds between stages. The example uses conservative exploratory stop
limits; an operator must also inspect worker restarts, queue age, database
headroom and host memory during each pause. A multi-stage production run
requires an interactive terminal and the operator must type `CONTINUE` after
each pause. The script refuses escalation if any route is unmeasured or exceeds
its steady-phase all-response p95 limit. The harness reports all-phase status
counts and a separate steady-phase latency summary. During a stage, any non-2xx response or timeout
stops new requests immediately; a route with at least 20 steady-phase samples above its
p95 limit also stops the stage. Requests already in flight can finish. It never submits orders. To include
controlled FINN chat, use separately approved accounts and add
`--include-chat --max-chat-requests 50`; the provisioned capacity fixture tokens
are restricted to four read routes and return 403 for chat. The script prints only
route-level status counts and latency summaries; it does not print tokens.
The identity preflight detects account-token mixups, but a separate owner-canary
test is still needed to prove isolation within workspace, FINN, and review bodies.

### Positive two-owner content check

For workspace and FINN conversation lists, create **two** new accounts with
the capacity provisioner, explicitly passing `--count 2` to `plan`, `create`,
`issue`, and `deactivate`; issue their tokens into a private 0700 directory.
Run `python -m backend.scripts.probe_capacity_owner_canary seed` from
`backend/trading-tool-backend` with the same campaign and verified DB host,
port and name, plus `--allow-production --apply` in production. It refuses
accounts with existing watchlist or FINN content, then inserts distinct XRP
and ADA watchlist rows and one visible, provider-free FINN conversation per
owner. Run `python3 ops/load/owner_canary.py --base-url https://tradamind.com
--fixtures /secure/path/two-owner-tokens.json --campaign CAMPAIGN
--allow-production` from the repo root. The probe reads each owner's identity,
workspace asset without a caller-supplied watchlist, and conversation list;
it fails if the other owner's symbol or conversation appears. No response
bodies or tokens are printed.

After the probe, run `python -m backend.scripts.probe_capacity_owner_canary cleanup` with
the same target flags and `--allow-production --apply`, then deactivate the
two marked accounts and delete the token file. Cleanup verifies exact owner,
message and marker fields and refuses to cascade-delete runs with dependent rows.
Production trade reviews currently use a separate allowlist; this canary
does not claim review-body isolation or real review-list capacity.

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
Marked fixture accounts are excluded from scheduled all-user dispatch, score
sync, and daily score generation. This keeps the read load from creating bot
execution or report work for synthetic users.

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
already issued tokens can still access the four read routes until expiry
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
