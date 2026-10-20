# 1000 active users: implementation and release plan

Baseline checked on 2026-10-20: the production backend and frontend both report
`191c1199b6129c8feb305657e7d3483d8eef4048`. That commit is `origin/main`.
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
3. Move to a host or host group with sufficient measured RAM before separating
   execution-critical, market/portfolio, scoring, and AI reporting workers.
   Keep FINN interactive isolated. Start with one process per class, then tune
   concurrency from observed queue age and RSS. Use a shared PostgreSQL and
   Redis broker/rate-limit store across hosts.

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
with agreed SLOs, no cross-account response, no unintended trade writes, and
the independent runtime verdict. The load harness is `ops/load/active_users.py`;
tokens remain in a local file outside Git.
