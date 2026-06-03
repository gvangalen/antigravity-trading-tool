# FINN Roadmap V4

Last updated: 2026-06-02

## Purpose

This document defines the product and engineering roadmap for FINN 4.0.

See also:

- [FINN Roadmap V3](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-roadmap-v3.md)
- [FINN Stable + Next Plan](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-stable-next-plan.md)

The goal of FINN 4.0 is to move beyond operator-grade routing, review, and prioritization and turn FINN into a deeply personal performance layer for the trader behind the system.

FINN 4.0 is not mainly about more automation.
It is about helping the user:

- learn from recurring outcomes
- understand personal strengths and failure modes
- turn journaling into usable intelligence
- manage the portfolio as a daily operating system
- receive coaching that is personal, evidence-backed, and timely

## Current Starting Point

FINN 4.0 starts from a much stronger base than FINN 3.0 did:

- `618fc35` is the current strongest FINN 3.0 live release
- latest full FINN 3.0 QA run:
  - Core: `89`
  - Operator: `82`
- `69/69` prompts returned `200`
- `0` generic failures
- operator routing is now broadly stable

That matters because FINN 4.0 does not need to rebuild the operator foundation. It can build upward from a system that already understands review, adherence, outcome tracking, portfolio signals, and priorities.

## Product Goal

FINN 4.0 should become a **Personal Trading Performance System**.

That means:

- FINN remembers what specific behavior patterns lead to good or bad outcomes
- FINN scores and explains personal trading performance over time
- FINN reads journal-style evidence as part of the decision loop
- FINN helps the user run the portfolio as a real operating desk
- FINN coaches the person, not only the trade

## Guiding Principles

### 1. Personal before autonomous

Before FINN gets more freedom to act, it should become much better at understanding the user’s own patterns, blind spots, and quality of execution.

### 2. Evidence-backed memory only

Memory, pattern claims, and performance feedback must stay tied to explicit events, journal entries, and outcome data.

### 3. Coaching must stay actionable

FINN 4.0 should not drift into vague psychology. It should produce concrete performance guidance:

- what pattern happened
- what it cost
- what rule to change
- what to do differently next time

### 4. One performance brain across surfaces

Outcome Memory, performance scoring, journal insight, portfolio posture, and coaching should come from shared internal layers, not one-off page logic.

### 5. Read-only trust still comes first

FINN 4.0 can become much more personal and influential without yet becoming autonomous. Keep judgment, explanation, and coaching ahead of execution authority.

## Delivery Sequence

## Phase 0 - 3.0 Stable Baseline

### Goal

Treat FINN 3.0 as stable enough to build on, without reopening broad operator architecture.

### Required before 4.0 execution

- current live baseline remains stable
- operator categories remain broadly healthy
- QA preflight remains mandatory for live measurement
- no new regressions in:
  - decision review
  - plan adherence
  - outcome tracking
  - portfolio intelligence
  - priority engine

### Exit criteria

- FINN 3.0 is treated as stable-by-default
- 4.0 work focuses on personal performance intelligence, not 3.0 rescue

## Phase 1 - Outcome Memory

### Goal

Turn repeated outcomes into reusable personal memory.

### Core behavior

FINN detects recurring patterns such as:

- repeated FOMO entries
- chasing after missed moves
- plan overrides
- adding to concentration
- stopping good behavior after a loss or win streak

### Output contract

- `memory_pattern`
- `supporting_evidence_count`
- `time_window`
- `behavioral_cost`
- `repeat_trigger`
- `recommended_rule`
- `confidence_level`

### Delivery shape

- extend current outcome tracking into durable pattern summaries
- store reusable memory snapshots instead of raw unbounded replay
- keep explicit links back to supporting governance and outcome events

### Primary first surfaces

- FINN coaching
- weekly/monthly reports
- Mission Control warnings
- review follow-up prompts

### Data additions

Add memory snapshots with:

- user id
- pattern family
- evidence count
- linked event ids
- time window
- estimated behavioral cost
- suggested protective rule
- confidence level
- last refreshed timestamp

### Exit criteria

FINN can say:

- what pattern keeps repeating
- how often it happened
- why it matters
- what rule should probably replace it

## Phase 2 - Personal Performance Layer

### Goal

Measure personal trading quality, not only trade outcomes.

### Core behavior

FINN builds a personal performance layer around:

- decision quality
- discipline quality
- follow-through quality
- recovery quality
- overtrading pressure
- patience and selectivity

### Output contract

- `performance_score`
- `score_breakdown`
- `performance_drivers`
- `discipline_delta`
- `recovery_status`
- `performance_risk_flags`
- `next_growth_target`

### Delivery shape

- create one canonical personal performance analysis layer
- compute rolling performance views for:
  - last 7 days
  - last 30 days
  - current month
- keep performance scoring explainable and decomposable

### Primary surfaces

- reports
- Mission Control
- personal coaching
- profile/performance dashboards

### Data additions

Add performance summaries with:

- scoring window
- component scores
- strongest positive pattern
- largest drag factor
- trend direction
- recommended next target

### Exit criteria

FINN can explain not just whether results were good, but whether the user traded well.

## Phase 3 - Trade Journal Intelligence

### Goal

Turn journal notes into structured intelligence instead of static logging.

### Core behavior

FINN reads and links journal-style content such as:

- why the trade was taken
- what the user feared
- what confirmation they waited for
- what they ignored
- what they learned afterward

### Output contract

- `journal_pattern`
- `journal_tags`
- `thesis_quality`
- `emotion_signal`
- `decision_gap`
- `post_trade_lesson`
- `journal_coaching_note`

### Delivery shape

- add structured extraction from journal entries and trade notes
- link journal entries to reviews, adherence events, and outcomes
- summarize across entries rather than only per single note

### Primary surfaces

- trade journal UI
- post-trade review
- weekly/monthly reports
- coaching prompts

### Data additions

Add journal intelligence records with:

- journal entry id
- linked trade/setup/strategy ids
- extracted tags
- emotion markers
- thesis summary
- lesson summary
- contradiction markers

### Exit criteria

FINN can tell the user what their own notes reveal that they are not consistently acting on.

## Phase 4 - Portfolio Operating System

### Goal

Make the portfolio the daily control object, not just one more context source.

### Core behavior

FINN treats the portfolio as an operating desk with:

- exposure concentration
- capital allocation pressure
- unresolved conflicts
- stacked active ideas
- action queues
- ignored but important risks

### Output contract

- `operating_posture`
- `portfolio_pressure`
- `capital_focus`
- `conflict_stack`
- `do_now`
- `do_next`
- `ignore_today`

### Delivery shape

- deepen the current 3.0 portfolio operating layer
- promote the portfolio to top-level object across Mission Control and reports
- unify personal performance and portfolio state in one operating picture

### Primary surfaces

- Mission Control
- reports
- bot and strategy drill-ins
- portfolio dashboards

### Data additions

Add portfolio operating snapshots with:

- posture
- top pressure source
- blocked actions
- priority actions
- capital concentration notes
- linked supporting modules

### Exit criteria

Users can open Tradamind and immediately understand the state of the portfolio as a system, not only the state of isolated trades.

## Phase 5 - Personal Coach

### Goal

Turn FINN into a genuinely personal trading coach.

### Core behavior

FINN combines:

- outcome memory
- performance scoring
- journal intelligence
- portfolio operating posture

to coach the user in a way that is:

- contextual
- evidence-backed
- behavior-specific
- timely

### Output contract

- `coach_mode`
- `current_pattern`
- `what_it_costs`
- `what_to_interrupt_now`
- `next_best_rule`
- `coach_follow_up`

### Delivery shape

- keep a shared coaching core across chat, reports, and Mission Control
- differentiate coach styles:
  - interruptive
  - reflective
  - recovery
  - pre-trade
  - post-trade

### Primary surfaces

- assistant chat
- Mission Control
- post-trade reviews
- reports
- personal performance views

### Data additions

Add coaching trace records with:

- coach mode
- source signals used
- recommended rule
- urgency
- follow-up suggestion
- supporting evidence references

### Exit criteria

FINN no longer feels like a generic assistant with trader language.
It feels like a coach that knows the user’s real habits and helps interrupt their worst loops.

## Shared Architecture Changes

FINN 4.0 should build on shared subsystems rather than isolated feature logic.

Required shared subsystems:

- `outcome_memory_engine`
- `personal_performance_engine`
- `journal_intelligence_engine`
- `portfolio_operating_engine`
- `personal_coach_engine`

Preferred location:

- continue anchoring orchestration in `FinnPlanService`
- extract stable helper modules only when logic is shared enough to deserve its own surface-independent boundary

## Public Interface Policy

Preferred rollout order:

1. expose new 4.0 intelligence through existing FINN assistant and report flows
2. surface it in Mission Control and performance/report surfaces
3. add dedicated endpoints only when the UI genuinely needs direct structured retrieval

Keep 4.0 read-mostly at first:

- no new autonomous actions required
- no silent execution coupling
- judgment and coaching remain the main delivery form

## Test Plan

### Core service tests

Add deterministic tests for:

- repeated negative outcome pattern becomes memory signal
- low evidence count stays low-confidence
- performance score explains its own drivers
- journal note extraction produces grounded tags and lessons
- portfolio operating posture changes when concentration/conflict changes
- personal coach chooses the right coaching mode for:
  - pre-trade stress
  - post-loss recovery
  - repeated override behavior

### Replay and QA coverage

Extend the FINN promptset with 4.0-style cases such as:

- "welk gedrag kost me de laatste maand het meeste?"
- "wat zegt mijn journal over mijn entries?"
- "waar verlies ik het meest discipline?"
- "wat is mijn grootste persoonlijke performance-lek?"
- "coach me op basis van mijn laatste fouten"

Do not relax 3.0 routing and operator gates while adding 4.0 capability.

### Product acceptance

A trader should be able to:

- see which behavior patterns keep repeating
- understand whether they traded well even if PnL was mixed
- turn journal notes into practical lessons
- run the portfolio as a daily operating system
- receive personal coaching that feels grounded and specific

## Phase Summary

### Phase 1 - Outcome Memory

FINN remembers repeated outcome patterns.

### Phase 2 - Personal Performance Layer

FINN measures whether the user is trading well, not just whether they won.

### Phase 3 - Trade Journal Intelligence

FINN turns journal notes into structured pattern and lesson extraction.

### Phase 4 - Portfolio Operating System

FINN helps run the whole portfolio as a live control layer.

### Phase 5 - Personal Coach

FINN becomes a personal trading coach grounded in evidence, memory, and performance.

## Definition of Done

FINN 4.0 is done when:

- behavior patterns are remembered across time
- performance is scored in a way the user can understand and trust
- journal content becomes useful intelligence
- the portfolio operates as the user’s daily decision desk
- coaching feels personal, specific, and grounded

## What Comes After 4.0

FINN 5.0 should start only after 4.0 is strong enough to justify more autonomy.

Likely 5.0 directions:

- semi-autonomous actions
- advanced portfolio allocation
- personal AI agents
- execution governance

That sequencing is intentional:

- 3.0 made FINN an operator layer
- 4.0 should make FINN personally effective
- 5.0 can then safely make FINN more powerful
