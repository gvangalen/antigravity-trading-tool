# FINN Trader Profile Release Note

Last updated: 2026-06-23

## Release

- branch: `codex/finn-product-sprint1-staging-candidate`
- staging commit certified: `df4e308`
- staging verdict: `go`
- weighted QA score: `91.5/100`

## Scope

This release completes the FINN trader-profile rollout across tranches 1-4.

Included outcome areas:

- durable trader-profile persistence via `assistant/preferences`
- profile-aware FINN context hydration and routing
- behavior-flag-aware coaching and explain flows
- broader legacy/general-help carryover
- memory / habit-aware interventions based on recent evidence
- behavioral telemetry from real FINN flows

## What is now visibly better

### 1. Profile-aware help is no longer metadata-only

The old weak spot was the legacy/general-help lane.
That lane now visibly adapts by profile in user-facing copy.

Examples:

- Calm swing trader:
  - `BTC op 4H/Daily bevestiging geeft. Blijf liever klein en selectief.`
- FOMO / overtrading profile:
  - `Wacht bij BTC eerst op bevestiging en stap niet in uit haast...`
- Exit-discipline profile:
  - `Check bij BTC eerst je invalidatie en uitstapgrens...`

### 2. Memory / habit copy is stronger and more evidence-based

The memory layer now does more than repeat static profile preferences.
It explicitly combines:

- stored behavioral flags
- recent usage activity
- governance / review evidence
- safe next-step rules

This makes interventions more credible on:

- `memory_step1`
- `memory_step2`
- `memory_step3`
- report explain
- coaching
- preflight / decision-review follow-ups

### 3. Telemetry supports the behavior story

Behavioral telemetry now climbs from real FINN usage, not only manual event posts.

Observed in the certified staging run:

- `behavioral_intervention_seen` increased from `66 -> 76`
- top behavioral surface remained `finn`

## QA result summary

Certified staging run on `df4e308`:

- preflight: green
- replay gate: `41/41 passed`
- generic failures: `0`
- transactional misroutes: `0`

Category scores:

- Profile Context Use: `5/5`
- Behavioral Coaching Quality: `4.5/5`
- Cross-Surface Consistency: `4.5/5`
- Memory / Habit Awareness: `4.5/5`
- Governance Safety / Friction Quality: `4/5`
- Telemetry / Observability Signal: `4.5/5`

Pass / partial / fail:

- profile persistence: `pass`
- profile-aware output: `pass`
- behavioral reminders on report: `pass`
- behavioral friction on bot/preflight: `pass`
- legacy assistant profile carryover: `pass`
- memory-aware intervention quality: `pass`
- telemetry visibility: `pass`
- misroute safety: `pass`

## Release reading

This is now a release-strong staging result, not just a technically healthy build.

The rollout is considered complete for the current FINN trader-profile scope because:

- persistence is correct
- the main product lanes are visibly profile-aware
- the legacy/help edge is no longer the weak point
- the memory layer is evidence-aware
- governance safety stayed intact
- telemetry confirms live behavioral interventions

## Recommended next work

This is no longer blocker work.
The next iteration can be treated as product improvement, not release rescue.

Best follow-ups:

1. strengthen governance-friction language from `4/5` toward `4.5-5/5`
2. deepen long-horizon memory quality with richer result / outcome evidence
3. widen UI-level observability surfaces beyond assistant-heavy traces
