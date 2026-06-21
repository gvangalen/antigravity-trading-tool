# Platform Phase 2.1 Capacity Harness

Last updated: 2026-06-06

## Purpose

This harness gives us a safe way to validate the current Phase 2.1 topology under controlled traffic.

It is intentionally conservative:

- no execute endpoints
- no report generation endpoints
- no live/manual order placement
- manual-order preview only when an explicit fixture is supplied

The goal is to measure:

- request latency under profile load
- queue/deep-health behavior before, during, and after a run
- whether the current worker topology stays calm enough under realistic V1 traffic
- first mixed-load behavior for a realistic staging user blend

## Script

- [run_platform_capacity_profiles.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_platform_capacity_profiles.py)

## Profiles

### `read-heavy`

Exercises read-biased surfaces:

- `/api/assistant/mission-control`
- `/api/report/daily/latest`
- `/api/report/daily/history`
- `/api/setups/top`
- `/api/market_data/BTC/latest`

### `ai-heavy`

Exercises read-only AI/report traffic:

- `/api/assistant/chat` with safe read-only prompts
- `/api/report/daily/preview`

### `bot-execution-heavy`

Exercises governance/preview-style traffic without real execution:

- `/api/bot/portfolios`
- `/api/assistant/chat` with governance prompts
- optional `/api/orders/preview` only when an explicit fixture is supplied

### `mixed-load`

Exercises the first platform-scale staging blend:

- `80% dashboard/read` users
- `15% FINN/AI` users
- `5% bot/governance-preview` users

The mixed profile reuses the same safe request families as the dedicated profiles:

- no execute endpoints
- no live/manual orders
- no report-generation writes

It also applies light, human-like pacing for FINN and governance traffic so mixed staging runs do not immediately collapse into artificial `429` noise from perfectly healthy rate limits.

## Usage

Bearer-token example:

```bash
export TT_USER_BEARER_TOKEN="<user-token>"
export TT_HEALTH_BEARER_TOKEN="<operator-token>"

python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_platform_capacity_profiles.py \
  --base-url https://tradamind.com \
  --bearer-token-env TT_USER_BEARER_TOKEN \
  --health-url https://tradamind.com/api/system/health \
  --health-bearer-token-env TT_HEALTH_BEARER_TOKEN \
  --profiles read-heavy ai-heavy bot-execution-heavy \
  --iterations 2 \
  --output-json /tmp/platform-phase2-1-capacity.json \
  --output-md /tmp/platform-phase2-1-capacity.md
```

Cookie-login example:

```bash
export TT_USER_PASSWORD="<password>"
export TT_HEALTH_BEARER_TOKEN="<operator-token>"

python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_platform_capacity_profiles.py \
  --base-url https://tradamind.com \
  --login-email "<email>" \
  --password-env TT_USER_PASSWORD \
  --health-url https://tradamind.com/api/system/health \
  --health-bearer-token-env TT_HEALTH_BEARER_TOKEN \
  --profiles read-heavy ai-heavy \
  --iterations 2 \
  --output-json /tmp/platform-phase2-1-capacity.json \
  --output-md /tmp/platform-phase2-1-capacity.md
```

Mixed staging baseline example:

```bash
export TT_USER_PASSWORD="<password>"
export TT_HEALTH_BEARER_TOKEN="<operator-token>"

python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_platform_capacity_profiles.py \
  --base-url https://staging.tradamind.com \
  --login-email "<email>" \
  --password-env TT_USER_PASSWORD \
  --health-url https://staging.tradamind.com/api/system/health \
  --health-bearer-token-env TT_HEALTH_BEARER_TOKEN \
  --profiles mixed-load \
  --virtual-users 100 \
  --iterations-per-user 1 \
  --read-share 80 \
  --ai-share 15 \
  --bot-share 5 \
  --mixed-concurrency 20 \
  --mixed-ai-think-time-seconds 2.5 \
  --mixed-bot-think-time-seconds 3.0 \
  --output-json /tmp/platform-scale-staging-mixed-100.json \
  --output-md /tmp/platform-scale-staging-mixed-100.md
```

If the local machine has a broken CA bundle for this environment, add `--insecure`.

## Optional manual-order preview fixture

Only use this when you explicitly want the `bot-execution-heavy` profile to include `/api/orders/preview`.

Required JSON fields:

```json
{
  "bot_id": 9,
  "symbol": "BTC",
  "side": "buy",
  "quantity": 0.001,
  "price": 50000
}
```

This still stays preview-only; it does not place an order.

## Output

The harness writes:

- JSON summary
- Markdown summary

Each run records:

- per-profile request count
- mixed-load virtual-user distribution when used
- mixed-load pacing settings when used
- success/failure counts
- avg/p95/max latency
- status distribution
- health snapshots before/during/after

## Operator notes

- Treat this as a capacity-validation harness, not a chaos test.
- Start with `iterations=1` or `2`.
- Use health snapshots to compare queue depth, degraded components, and cluster-observability metadata.
- If `/api/system/health` is not reachable with operator auth, the harness still runs traffic but marks health snapshots as skipped.
