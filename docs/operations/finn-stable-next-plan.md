# FINN Stable + Next Plan

Last updated: 2026-05-31

## Decision

Treat `852232c` as the current `FINN 2.0 Stable` baseline.

This decision is based on two complete live QA runs confirming the same score level:

- `efc4de3` -> `86/100`
- `852232c` -> `86/100`

That matters more than chasing a one-off higher run, because it shows FINN is now stably good rather than occasionally lucky.

## Confirmed Baseline

Current stable baseline:

- overall score: `86/100`
- `49/49` responses returned `200`
- `20/20` stress prompts returned `200`
- `0` generic failures
- `0` transactional misroutes

Strong categories:

- trading knowledge
- product knowledge
- reliability

Improved categories that now hold at a good level:

- context awareness
- coaching
- data refresh routing

Reference artifacts:

- [/tmp/finn-live-eval-efc4de3-full.json](/tmp/finn-live-eval-efc4de3-full.json)
- [/tmp/finn-live-eval-852232c-full.json](/tmp/finn-live-eval-852232c-full.json)

## Working Rules

Use the stable baseline this way:

- below `86` = regression alert
- `86` = baseline held
- `90+` = new quality milestone

Do not treat health-only or replay-only wins as a new FINN score baseline.

## Next Sprint

Run one short polish sprint focused only on the last high-impact gaps:

1. mixed-session context precision
2. overtrading -> direct coach
3. latency outliers where fast wins are available

This is intentionally a narrow sprint, not another broad rewrite.

## Why This Sprint Is Worth Doing

The current gap to `90+` is now small and concrete:

- mixed-session setup/strategy follow-ups can still become too cautious
- overtrading still feels weaker than the stronger FOMO/emotional/deviation coaching paths
- latency is generally healthy, but long-tail spikes still hurt the premium feel

If those three areas improve, `90+` becomes a credible next milestone rather than a vague ambition.

## Next-Gen Focus

After the polish sprint, move the main focus away from QA-point chasing and toward trader impact.

Priority direction:

- better decision support
- stronger review and follow-through flows
- clearer "what now" guidance
- better framing of risk, doubt, and trade-offs
- features that help traders make better daily decisions

Execution reference:

- [FINN Roadmap V3](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-roadmap-v3.md)

## Product Strategy Reminder

At this stage, another month of broad QA optimization is likely less valuable than building the next layer of practical trader help.

The sequence should now be:

1. protect the stable baseline
2. run one short polish sprint
3. shift toward next-generation user value

One of the clearest next-value tracks is:

- [FINN Onboarding Trader Profile Plan](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-onboarding-trader-profile-plan.md)

## Short Version

- `852232c` = `FINN 2.0 Stable`
- `86/100` = confirmed live baseline
- one more small sprint for:
  - mixed-session context
  - overtrading coaching
  - latency outliers
- then move primary effort to trader-facing value

## Current Evolution

That next step is now real:

- FINN 3.0 is the current stable direction
- the next roadmap focus is now:
  - [FINN Roadmap V4](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-roadmap-v4.md)
- the next certification push is:
  - [FINN Certification Push Plan](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-certification-push-plan.md)
