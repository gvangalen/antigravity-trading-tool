# 1000 active users: implementation and release plan

Baseline checked on 2026-10-20: the production backend and frontend both report
`e26a1b4d049a1aa57bd19f96503e2b79155fbe99`. That commit records the
FINN V2 cutover deployment; the product code baseline is its parent `191c1199`.
The production ecosystem configuration says the host has 1 GB RAM and records
worker OOMs from an earlier multi-process layout. Treat the current host as a
capacity constraint, not as proof that another worker split is safe.

The clean `active-users-main` worktree contains the Release 1 code changes,
cluster metrics, a read-only load harness, and database pool reductions. Local
backend tests and frontend build pass. These changes are not deployed or
capacity-proven. The live environment has no 1000-account fixture file yet.

## Release 1: correctness on the current main branch

1. Port the account-scoped workspace cache and logout invalidation to current
   `main`. Test A -> logout -> B in one browser session, including a delayed A
   response, and verify that no A snapshot appears in B's view.
2. Move auth, FINN, order, and review rate limits to atomic Redis counters with
   bounded TTLs and safe proxy-IP handling. Verify two API processes share one
   limit; verify the defined behavior when Redis is unavailable.
3. Make dispatcher backlog admission atomic per task, account for scheduled
   tasks, and continue large waves without dropping users. Verify a 1000-user
   wave never exceeds the configured admission limit and eventually drains.
4. Remove write-on-read from trade-review GET and pause unnecessary polling in
   hidden tabs and after terminal states. Verify the GET causes no database
   writes and old chart failures do not trigger continuous retries.
5. Optimize measured workspace queries, starting with duplicate asset catalog
   reads. Measure authenticated route p50/p95, query counts, and database pool
   occupancy before and after.

## Release 2: observable capacity

1. Add cluster-wide Redis metrics for request latency, retry and dispatcher
   counters. Keep the deep health endpoint diagnostic rather than a frequent
   request-path or strict readiness check.
2. Measure actual production memory, CPU, queue age, database connection
   ceiling, and provider quotas. Budget every proposed API and worker process.
3. Move to a host or host group with sufficient measured RAM before selecting
   `scaled` in `ops/deploy/capacity_profile.json`. The deploy preflight rejects
   a scaled topology below 6 GiB RAM. The scaled profile gives execution,
   market/portfolio, scoring, AI reporting, and FINN interactive separate
   workers, with two API processes and a default maximum of 70 database
   connections against a budget of 80. Measure RSS and queue age before
   increasing concurrency. Use a shared PostgreSQL and Redis broker/rate-limit
   store across hosts.

## Release and capacity gate

Build a clean candidate from current `origin/main`; do not deploy the old local
branch or its multi-worker defaults to the 1 GB production host. Complete the
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
meeting these provisional gates: workspace p95 at most 2 seconds, FINN-state
and trade-review reads p95 at most 1 second, under 0.1% 5xx responses, no
normal-traffic 429s, no growing queue age, and at least 20 database connections
of headroom. Confirm the thresholds with product/operations before the test.
There must be no cross-account response or unintended trade write, and the
independent runtime verdict must pass. The load harness is `ops/load/active_users.py`;
tokens remain in a local file outside Git.
