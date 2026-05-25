# Platform Hardening Step 5 - Frontend Cache And Polling

Date: 2026-05-25

## Goal

Reduce frontend read amplification without changing the product contract. The app should still refresh operator-critical data, but it should stop forcing every authenticated GET through `no-store` and should avoid polling aggressively while hidden.

## Changes

- `apiGet` now uses a method-aware cache policy:
  - GET defaults to browser `default` cache behavior.
  - POST/PUT/DELETE still default to `no-store`.
  - Callers can force fresh reads with `forceFresh` or explicit `cache`.
- `fetchAuth` follows the same method-aware cache policy.
- `no-store` cache-control headers are only sent when the resolved cache mode is `no-store`.
- `useDashboardData` now uses adaptive polling:
  - foreground interval: 120 seconds
  - background interval: 300 seconds
  - refreshes immediately when the tab becomes visible
  - prevents overlapping dashboard loads with a single-flight guard

## Safety Boundary

This does not cache mutating requests. It also does not introduce a shared server cache. It only removes the unconditional client-side `no-store` behavior for GET helpers and reduces idle-tab polling pressure.

Freshness-sensitive callers can still opt into:

```ts
apiGet("/api/path", { forceFresh: true })
apiGet("/api/path", { cache: "no-store" })
fetchAuth("/api/path", { cache: "no-store" })
```

## Regression Coverage

`backend/tests/test_frontend_cache_polling_policy.py` checks:

- GET helpers no longer hard-force `no-store`.
- `fetchAuth` uses the same method-aware policy.
- dashboard polling is visibility-aware and no longer fixed at 60 seconds.

