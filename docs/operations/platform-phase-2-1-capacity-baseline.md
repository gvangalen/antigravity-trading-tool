# Platform Phase 2.1 Capacity Baseline

Last updated: 2026-06-06

## Goal

Capture the first safe, repeatable capacity baseline for the current Phase 2.1 platform state.

This baseline is intentionally modest:

- small profile runs
- no execute endpoints
- no report generation writes
- governance-only bot/execution profile

It is meant to answer:

- which profile family is already operationally calm
- which profile family is the current throughput bottleneck
- whether deep health remains readable during controlled profile traffic

## Runtime Baseline

- `repo_head`: `c911850`
- `production_head`: `8096336`
- `LAST_GOOD_COMMIT`: `8096336`

Note:

- the capacity harness health-probe fix lives on `main` in `c911850`
- the measured traffic profiles below were run safely against the live production baseline that was already up
- the results are still useful as a first platform baseline because the fix only changed health snapshot collection, not traffic behavior

## Harness

- script: [run_platform_capacity_profiles.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_platform_capacity_profiles.py)
- operator note: [Platform Phase 2.1 Capacity Harness](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-capacity-harness.md)

## Profile Results

### 1. Read-heavy

Artifacts:

- [/tmp/platform-phase2-1-capacity-read-heavy-v3.json](/tmp/platform-phase2-1-capacity-read-heavy-v3.json)
- [/tmp/platform-phase2-1-capacity-read-heavy-v3.md](/tmp/platform-phase2-1-capacity-read-heavy-v3.md)

Summary:

- `request_count = 5`
- `success_count = 5`
- `failure_count = 0`
- `avg_latency_ms = 4406.74`
- `p95_latency_ms = 12024.15`
- `max_latency_ms = 14487.39`

Health behavior:

- `before = 200 / ok`
- `during = 200 / ok`
- `after = 200 / ok`
- queue depth stayed broadly flat: `369399 -> 369395`

Reading:

- operationally clean
- still noticeably heavy
- read surfaces are stable, but not cheap

### 2. AI-heavy

Initial run artifacts:

- [/tmp/platform-phase2-1-capacity-ai-heavy-v1.json](/tmp/platform-phase2-1-capacity-ai-heavy-v1.json)
- [/tmp/platform-phase2-1-capacity-ai-heavy-v1.md](/tmp/platform-phase2-1-capacity-ai-heavy-v1.md)

Confirm run artifacts:

- [/tmp/platform-phase2-1-capacity-ai-heavy-v2.json](/tmp/platform-phase2-1-capacity-ai-heavy-v2.json)
- [/tmp/platform-phase2-1-capacity-ai-heavy-v2.md](/tmp/platform-phase2-1-capacity-ai-heavy-v2.md)

Initial run summary:

- `request_count = 4`
- `success_count = 4`
- `failure_count = 0`
- `avg_latency_ms = 12008.21`
- `p95_latency_ms = 22445.03`
- `max_latency_ms = 23188.63`

Health behavior:

- `before = 200 / ok`
- `during = 200 / ok`
- `after = 200 / ok`
- queue depth eased slightly: `369243 -> 369213`

Confirm run summary:

- `request_count = 8`
- `success_count = 8`
- `failure_count = 0`
- `avg_latency_ms = 13138.22`
- `p95_latency_ms = 30392.16`
- `max_latency_ms = 34103.99`

Confirm-run health behavior:

- `before = 200 / degraded`
- early health snapshots showed `broker` degradation
- later snapshots recovered to `200 / ok`
- `after = 200 / ok`
- queue depth eased further: `368854 -> 368832`

Reading:

- content/runtime stayed stable
- this is the clear slowest profile family
- the heavier confirm-run strengthens that conclusion instead of weakening it
- AI-heavy traffic is also the first profile that meaningfully overlaps with the known broker/deep-health wobble
- current Phase 2.1 throughput tension sits here first

### 3. Bot-execution-heavy

Mode:

- governance/preview-only
- no real execute flow
- no order placement

Artifacts:

- [/tmp/platform-phase2-1-capacity-bot-heavy-v1.json](/tmp/platform-phase2-1-capacity-bot-heavy-v1.json)
- [/tmp/platform-phase2-1-capacity-bot-heavy-v1.md](/tmp/platform-phase2-1-capacity-bot-heavy-v1.md)

Summary:

- `request_count = 4`
- `success_count = 4`
- `failure_count = 0`
- `avg_latency_ms = 183.25`
- `p95_latency_ms = 357.48`
- `max_latency_ms = 377.48`

Health behavior:

- `before = 200 / ok`
- `during = 200 / ok`
- `after = 200 / ok`
- queue depth stayed effectively flat: `369181 -> 369177`

Reading:

- clearly the calmest profile
- governance/preview paths are not the current bottleneck
- good sign for the safety layer under controlled traffic

## Overall Reading

This first baseline says:

1. `bot-execution-heavy` is healthy and lightweight in preview/governance mode
2. `read-heavy` is stable but still somewhat expensive
3. `ai-heavy` is the current throughput hotspot, and the confirm-run makes that conclusion much harder to dismiss

That means the next optimization pass should focus on:

- Mission Control and assistant-heavy read paths
- report preview / AI-heavy latency
- not on bot governance or preview safety paths first

## Recommended Next Step

1. use the confirm-run as the current AI-heavy reference
2. inspect the slowest assistant/report-preview paths specifically
3. only after that decide whether worker concurrency should move again or whether path-level slimming gives better ROI
4. track the next action list in [Platform Phase 2.1 AI-heavy Optimization Checklist](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-ai-heavy-optimization-checklist.md)
