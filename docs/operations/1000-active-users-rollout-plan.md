# 1000 active users: implementation and release plan

Latest verified production baseline on 2026-10-20: backend health and frontend
build info both returned HTTP 200 and SHA
`0755a9c402565a9c8641ea8d43d34aae036d007b`. The scaled topology has
two API workers and separate critical/market/scoring/AI/FINN workers.
Independent QA owner canaries passed for workspace and FINN conversation
content; trade-review body ownership remains unproven because canary lists
were empty. No order or FINN action route was load-tested.
The production ecosystem configuration records worker OOMs from an earlier
multi-process layout on a 1 GB host. A read-only SSH check on 2026-10-20 of
the production host found 4 vCPU and 8,125,916 KiB
(7.75 GiB) RAM, with 6,054 MiB available and no swap at idle. PostgreSQL
reported `max_connections=100` and 19 active connections. PM2 showed five
online compact-profile processes at that earlier check. This is the current 7.75 GiB host, not the
historical 1 GiB host.

Independent QA repeated the live read workload on `52ef2159` with 1,000
distinct marked accounts. The 100-user stage completed with all 1,302 HTTP
responses successful and steady p95 of 66/9/18 ms for workspace/FINN list/
trade-review list. The 500-user stage completed with all 6,501 responses
successful and steady p95 of 366/121/191 ms. The 1,000-user stage stopped
early after four HTTP 500s and p95 breaches on all routes. The API's single
async SQLAlchemy pool exhausted its 10 base plus five overflow connections
with a three-second checkout timeout; PostgreSQL had at most 20 of 100
connections in sampled measurements, more than 5.83 GiB RAM remained
available, queues were empty, and PM2 recorded no restarts. All synthetic
accounts were deactivated and private token files removed after each run.
Therefore 1,000 active users were **not accepted** on compact topology.
Independent QA then measured the scaled topology on `0755a9c4`: the 100-user
and 500-user stages passed with all 1,308 and 6,492 requests returning HTTP
200. Steady p95 for workspace/FINN list/review list was 74/10/29 ms at 100
and 162/23/50 ms at 500. The 1,000-user stage stopped early after one review
HTTP 500 and p95 breaches on all three routes. One API worker exhausted its
local 10+5 async database pool; sampled PostgreSQL occupancy peaked at 49/100,
CPU at 63%, and MemAvailable remained above 4.18 GiB. All fixture accounts
were deactivated and private token files removed. The next candidate removes
the remaining review GET write, skips weekly work for empty owners, batches
workspace coverage reads, and increases each API worker's async pool from
15 to 20 slots within an 80-connection configured maximum. A new full live test is required before a
1,000-active-user claim. Deep health exposes dispatcher reservation
count and one-hour age by queue.
`backend/scripts/reconcile_dispatch_reservations.py` reports stale task IDs
and can release terminal reservations directly. Routine reconciliation leaves
`PENDING`, `STARTED`, and `RETRY` untouched. If those remain stale, inspect
the task ID in broker, worker active/reserved/scheduled state, and result
backend before any manual repair; do not delete its Redis reservation merely
because a worker is slow or an inspect call times out. Run from the backend
directory with `python3 -m backend.scripts.reconcile_dispatch_reservations`
for read-only inventory and add `--apply-terminal` to clear verified terminal
results. A nonzero exit means unresolved stale reservations require attention.
Celery Beat runs `monitor_dispatch_reservations` every five minutes and emits
a critical worker log plus a cluster counter for each queue with reservations
older than one hour. The deployment operator owns this signal during rollout;
production operations must route that log/counter to their alert channel.
For a confirmed lost nonterminal task on the current single-host deployment,
stop Celery Beat and all Celery workers, verify the trade/order or other
business effect by task ID, then run the tool with `--queue QUEUE
--release-lost-task-id TASK_ID --fenced-single-host
--business-effect-verified --acknowledge-possible-redelivery
--audit-log /secure/path/dispatcher-recovery.jsonl
--reason 'incident reference and verified business outcome'`. It refuses to
release if any local Celery process is running, any worker responds on the
broker, the task appears in the broker queue or Redis unacked hash, or the
result is terminal. It checks twice five seconds apart and writes private,
fsynced intent before mutation and completion afterward. This procedure is
only valid when operations have established that no other host runs workers
against the broker; for a multi-host deployment, fence every host before
adapting this recovery process. Restart workers and Beat after repair.
The load harness verifies each token's account identity and aborts
escalation on HTTP errors, but owner canaries for each data route and sustained
live worker traffic remain separate acceptance work.

## Release 1: correctness on the current main branch

1. Port the account-scoped workspace cache and logout invalidation to current
   `main`. Test A -> logout -> B in one browser session, including a delayed A
   response, and verify that no A snapshot appears in B's view.
2. Move auth, FINN, order, and review rate limits to atomic Redis counters with
   bounded TTLs and safe proxy-IP handling. Verify two API processes share one
   limit; verify the defined behavior when Redis is unavailable.
3. Make dispatcher backlog admission atomic per task, account for scheduled
   tasks until completion, and continue large waves without dropping users. Verify a 1000-user
   wave never exceeds the configured admission limit and eventually drains.
4. Remove write-on-read from trade-review GET and pause unnecessary polling in
   hidden tabs and after terminal states. Verify the GET causes no database
   writes and old chart failures do not trigger continuous retries.
5. Optimize measured workspace queries, starting with duplicate asset catalog
   reads. Measure authenticated route p50/p95, query counts, and database pool
   occupancy before and after.

## Release 2: observable capacity

1. Use cluster-wide Redis metrics for existing service latency, retry and
   dispatcher counters; take HTTP route latency and error rates from the load
   harness. Keep deep health out of the request path, but require registered
   queue consumers at deployment.
2. Recheck production memory, CPU, queue age, database connection occupancy,
   and provider quotas under load. Budget every proposed API and worker process.
3. Select `scaled` in `ops/deploy/capacity_profile.json` only after verifying
   the current host or host group has enough RAM. The deploy preflight rejects
   a scaled topology below 6 GiB RAM. The scaled profile gives execution,
   market/portfolio, scoring, AI reporting, and FINN interactive separate
   workers. The next candidate retains two API processes and a default maximum
   of 80 database connections against a budget of 80. Measure RSS and queue age before
   increasing concurrency. Use a shared PostgreSQL and Redis broker/rate-limit
   store across hosts.

## Release and capacity gate

Build a clean candidate from current `origin/main`; measure live resource
headroom under load before enabling a multi-worker topology. Complete the
applicable FINN local action-contract, provider, backend, frontend, and CI
gates before Auto Deploy. After deploy, Build checks only deployment success,
backend HTTP 200, frontend build info, and matching SHA. Independent QA owns
the authenticated production runtime verdict; Security and Architecture
provide their independent reviews.

With 1000 distinct fixture accounts on the authorized live environment, run
read-heavy stages at 100, 500, and 1000 simultaneous users. Record route p50,
p95, 5xx and 429 counts, queue depth and age, RSS and CPU, PostgreSQL
connections and slow queries, and provider errors. Abort escalation on rising
error or queue-age trends. A 1000-active-user claim requires a sustained stage
meeting these provisional gates: workspace p95 at most 2 seconds, FINN-conversation
and trade-review reads p95 at most 1 second, under 0.1% 5xx responses, no
normal-traffic 429s, no growing queue age, and at least 20 database connections
of headroom. Confirm the thresholds with product/operations before the test.
There must be no cross-account response or unintended trade write, and the
independent runtime verdict must pass. The load harness is `ops/load/active_users.py`;
tokens remain in a local file outside Git.
