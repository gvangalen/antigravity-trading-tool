# Tradamind Overview And Market Performance Plan

Last updated: 2026-06-17

## Purpose

This plan turns the recent live slowness around `Overview`, `Market`, and FINN-adjacent surfaces into a structural performance program.

The goal is not another quick fix.
The goal is to make the platform predictably fast by reducing read amplification, simplifying frontend fetch behavior, and making backend market reads cheaper by design.

## Current Reading

What we now know from live behavior and recent fixes:

- the site can recover quickly once the worst hotspots are trimmed
- the worst pain is not one single broken route, but too many expensive reads landing at once
- `Overview` still tries to assemble a lot of intelligence very early
- market endpoints are central to many cards and widgets
- FINN overlay can now be usable, but page-level slowness still leaks into the product feel

We also confirmed that:

- `market_data latest` reads benefit from DB indexing
- frontend mounts still matter a lot for perceived speed
- the user experience suffers when heavy panels fetch before the user actually needs them

## Problem Definition

The current slowness is mostly a combination of:

1. too many parallel market/intelligence reads on page load
2. heavy dashboard panels mounting too early
3. insufficient request sharing on the client
4. repeated reads for near-identical data
5. backend queries that are still more expensive than they need to be

This creates a bad pattern:

- the page shell appears
- too many components start fetching at once
- retries and slow endpoints pile up
- the app feels unstable even when health checks are green

## Long-Term Goal

For `Overview` and `Market`, the user should feel:

- fast first paint
- clear progressive loading
- no blank heavy waits
- no obvious refetch storms
- no need to load deep analysis before the user asks for it

Operationally, we want:

- fewer concurrent reads per page load
- more cache reuse on the client
- clearer freshness classes per endpoint
- lower DB load for common market reads
- better visibility into which panels actually cost time

## Strategic Direction

### 1. Frontend Fetch Budget

Every major page should have an explicit fetch budget.

For `Overview`, that means:

- first paint only loads:
  - shell
  - top scores/status
  - minimal latest market snapshot
- secondary panels load after a short delay or on visibility
- deep analysis loads only when:
  - the user scrolls to it
  - or explicitly expands it

### 2. Shared Read Model

We should stop letting each component fetch its own slightly different version of the same truth.

The preferred shape is:

- one lightweight page-level market snapshot
- one deferred intelligence payload
- one explicit deep-analysis payload

This lowers:

- duplicate fetches
- overlapping retries
- inconsistent state between cards

### 3. Freshness Classes

Not all reads need the same freshness.

We should classify endpoints into:

- `live-critical`
  - examples: latest price, active review count
- `session-fresh`
  - examples: market intelligence summary, daily scores
- `deferred`
  - examples: score history, long-horizon forward data, archived activity

Each class gets its own:

- cache TTL
- retry policy
- mount timing
- polling behavior

### 4. Backend Query Discipline

The backend should optimize for the common read path, not only correctness.

That means:

- keep the new `market_data` indexes
- review other hot query shapes used by `Overview` and `Market`
- prefer compact read models over repeated wide-table reads
- add pre-aggregated summary endpoints where the frontend only needs summary data

### 5. Observability For Page Cost

We need to know which page surface is expensive, not just whether the whole app is “up”.

We should track:

- per-endpoint response time
- per-panel mount latency
- total dashboard boot time
- retry count by endpoint
- cache hit ratio for market/intelligence hooks

## Workstreams

## Workstream A - Overview Fetch Budget

### Goal

Reduce the amount of work done during the first 2 seconds of `Overview`.

### Changes

- keep only lightweight cards in the initial render path
- defer:
  - score history
  - deep analysis
  - secondary intelligence panels
- load some panels only when visible

### Acceptance

- `Overview` first paint feels immediate
- no deep analysis requests before the user reaches that area
- no obvious spinner wall during first load

## Workstream B - Shared Client Data Layer

### Goal

Stop multiple components from issuing overlapping reads for the same market state.

### Changes

- use one page-level shared snapshot for:
  - latest market data
  - score summary
  - core intelligence summary
- keep hook-level caches and inflight dedupe
- move repeated fetch logic into shared helpers where useful

### Acceptance

- opening `Overview` does not create duplicate latest-price or intelligence reads
- multiple cards reuse the same data source where possible

## Workstream C - Deferred And On-Demand Data

### Goal

Make long-tail data opt-in instead of default.

### Changes

- load `score history` only:
  - after delay
  - or after user interaction
- load `forward month/quarter/year` only when needed by visible panels
- do not request extended datasets on every page boot if only one card needs them

### Acceptance

- no heavy history/forward dataset fetches on first boot unless visible/needed
- console no longer fills with parallel market-load failures during cold load

## Workstream D - Market API Efficiency

### Goal

Keep the most frequent market endpoints consistently cheap.

### Changes

- preserve and verify the new `market_data(symbol, timestamp DESC)` index
- inspect other hot read paths:
  - forward week/month/quarter/year
  - daily score history
  - market intelligence summary
- add compact summary endpoints if the frontend only needs a small subset

### Acceptance

- latest market snapshot stays low-latency under normal load
- forward market reads stop dominating perceived page load

## Workstream E - Retry And Failure Policy

### Goal

Make failures cheaper and less noisy.

### Changes

- lower retry cost for non-critical reads
- keep user-facing retries only where they actually help
- silence or downshift noisy console warnings for expected transient misses
- use cached data as fallback where safe

### Acceptance

- fewer retry storms
- fewer visible load cascades from one slow endpoint
- cleaner operator console during normal page use

## Workstream F - Page Performance Observability

### Goal

Measure page cost directly.

### Changes

- add metrics for:
  - `overview_shell_ready_ms`
  - `overview_primary_cards_ready_ms`
  - `overview_deep_analysis_ready_ms`
  - `market_latest_fetch_ms`
  - `market_forward_fetch_ms`
  - `intelligence_cache_hit`
  - `scores_cache_hit`
- expose a compact operator view or system log summary for these values

### Acceptance

- we can tell whether a slowdown is:
  - frontend mount timing
  - market endpoint latency
  - retry amplification
  - or DB cost

## Recommended Priority Order

### P0

1. Overview fetch budget
2. Deferred/on-demand data
3. Shared client data layer

These are the biggest wins for perceived speed.

### P1

4. Market API efficiency
5. Retry and failure policy

These reduce backend pressure and noisy failure cascades.

### P2

6. Page performance observability

This is essential for durability, but it becomes most useful once the main read budget is already cleaner.

## Immediate Implementation Tranche

The next concrete tranche should be:

1. keep `Overview` shell + primary status cards in the first render path
2. lazy-load deep analysis and score history
3. stop requesting extended market datasets before visible demand
4. centralize shared latest/intelligence snapshots
5. verify cache hit behavior on live

## Acceptance Criteria

We consider this plan successful when:

- `Overview` feels fast without waiting for deep analysis
- `Market` no longer produces obvious parallel fetch storms
- live operator use stops seeing recurring “load failed” bursts on normal visits
- frontend still feels fresh enough for trading context
- backend market endpoints stay stable under repeated user navigation

## Non-Goals

This plan does not aim to:

- redesign FINN overlay again
- remove useful analysis features
- over-cache mutation-sensitive data
- replace correctness with stale snapshots

The point is not to show less intelligence.
The point is to load it at the right moment and from the right layer.
