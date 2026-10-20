# 1000 active users: implementation and release plan

Baseline checked on 2026-10-20: the production backend and frontend both report
`1f7077ea179bbf1ef0887be4605d731df73af880`. This includes the recent
FINN cutover QA repair and feed update. The capacity candidate includes that
`main` revision.
The production ecosystem configuration records worker OOMs from an earlier
multi-process layout on a 1 GB host. A read-only SSH check on 2026-10-20 of
the host serving the current production SHA found 4 vCPU and 8,125,916 KiB
(7.75 GiB) RAM, with 6,054 MiB available and no swap at idle. PostgreSQL
reported `max_connections=100` and 19 active connections. PM2 showed five
online compact-profile processes. These point-in-time observations establish
that the current host is larger than the historical one; they do not prove
capacity under load.

The isolated `active-users-main` worktree contains the Release 1 code changes,
cluster metrics, a read-only load harness, and database pool reductions. The
combined backend suite passed 3543 tests with 3 skips. The combined frontend
build, typecheck, focused tests and production audit passed. The isolated FINN
action matrix passed 16/16 contracts and 19/19 adapter tests after the merge;
real-provider selector development and regression passed 20/20 and 109/109
cases on unchanged selector code. CI passed all five jobs on the first merged
candidate and on the provisioner candidate `c216d99aa`. See
`docs/agents/FINN_RELEASE_STATUS.md`
for artifact hashes. These changes are not deployed or capacity-proven. The
live environment has no 1000-account fixture file yet. A marked account
provisioner is prepared but has not been run against production; its tokens
are restricted to the three load reads plus account identity. Local creation,
issuance and deactivation of 1000 accounts passed; production accounts remain
uncreated. Independent reviews found that synthetic users entered scheduled
jobs and deployment could pass without worker readiness. The candidate now
excludes marked users from those jobs, holds dispatcher reservations until
task completion, and requires queue consumers at deployment. Independent QA,
Security, and Architecture re-reviews found no remaining P1 code blocker;
live QA remains pending. Deep health now exposes reservation count and one-hour
age by queue.
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
   workers, with two API processes and a default maximum of 70 database
   connections against a budget of 80. Measure RSS and queue age before
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
