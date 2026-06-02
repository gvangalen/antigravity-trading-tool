# FINN Roadmap V3

Last updated: 2026-05-31

## Purpose

This document defines the product and engineering roadmap for FINN 3.0.

See also:

- [FINN 3.0 Operator Fix Backlog V2](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-3-operator-fix-backlog-v2.md)

The goal of FINN 3.0 is to move beyond:

- routing
- explanation
- page context
- reactive coaching

and turn FINN into the decision, discipline, and portfolio control layer above Tradamind.

FINN 3.0 is not primarily about adding more indicators, more agents, or more prompt coverage.
It is about helping traders:

- make better decisions
- stay inside their plan
- understand what behavior costs them quality
- prioritize the right action at the right time
- manage risk at portfolio level

## Current Starting Point

Current stable foundation:

- `852232c` is the current `FINN 2.0 Stable` baseline
- stable full live QA baseline: `86/100`
- no generic failures
- no transactional misroutes
- strong trading knowledge, product knowledge, and reliability

That means FINN 3.0 does **not** start from a broken assistant. It starts from a stable operator-grade assistant that still needs one last 2.x polish pass before the next-gen layer should become the main focus.

## Product Goal

FINN 3.0 should become a **Trading Operating System**.

That means:

- FINN evaluates actions before they happen
- FINN measures whether users follow their own plan
- FINN links behavior to outcomes
- FINN prioritizes at portfolio level
- FINN becomes the daily control layer above setups, strategies, bots, reports, and exposure

## Guiding Principles

### 1. Operator-first rollout

Build the judgment engine first as a read-only internal layer, then expose it more broadly through chat, Mission Control, and reporting.

### 2. Decision quality before automation breadth

Do not broaden execution scope before review quality, adherence quality, and portfolio risk quality are strong.

### 3. Deterministic where trust matters

Review outcomes, plan checks, blockers, and portfolio constraints should remain deterministic and auditable.

### 4. Evidence before personalization

Memory, pattern detection, and outcome coaching must be grounded in explicit events and sufficient sample sizes.

### 5. One FINN brain

Do not create separate decision logic for chat, Mission Control, reports, and coaching. Build shared internal judgment layers and reuse them across surfaces.

## Delivery Sequence

## Phase 0 - 2.x Stabilization Gate

### Goal

Protect the stable FINN 2.0 baseline before starting broader 3.0 work.

### Required before 3.0 execution

- stable baseline remains at least `86/100`
- no regression in:
  - context awareness
  - coaching
  - refresh routing
  - reliability
- FINN QA preflight remains mandatory
- replay gate remains green

### Exit criteria

- stable baseline held
- QA runs are trustworthy again
- no unresolved production-runtime blocker on the current stable release

## Phase 1 - Decision Review Engine

### Goal

Let FINN review a proposed trade, setup, strategy action, or bot decision before execution.

### Core behavior

FINN evaluates a candidate action against:

- setup validity
- strategy rules
- risk profile
- budget and size constraints
- active blockers
- portfolio exposure

### Output contract

- `review_type`
- `decision_status`
  - `approve`
  - `modify`
  - `block`
  - `insufficient_context`
- `checks[]`
- `top_blockers[]`
- `recommended_changes[]`
- `risk_summary`
- `operator_next_step`

### Delivery shape

- build one canonical review builder in `FinnPlanService`
- keep it read-only
- reuse existing context/state hydration and product data fetches
- no silent execution from this phase

### Primary first surfaces

- FINN chat
- bot decision review
- setup/strategy page explain
- Mission Control drill-in

### Data additions

Add a review snapshot entity with:

- subject type
- subject id
- asset
- triggered checks
- outcome
- top blocker
- recommendation summary
- timestamp

### Exit criteria

FINN can deterministically review:

- manual trade intent
- bot decision intent
- setup readiness
- strategy fit

## Phase 2 - Plan Adherence System

### Goal

Turn review into behavior governance.

### Core behavior

FINN measures whether actions match the user’s own plan and classifies:

- in-plan
- outside plan
- forced override
- insufficiently justified

### Output contract

- `adherence_status`
- `adherence_reason`
- `threatened_rule`
- `override_detected`
- `discipline_score`
- `week_delta`
- `suggested_recovery_step`

### Delivery shape

- define explicit plan-rule extraction from:
  - setup
  - strategy
  - bot config
  - declared risk profile
- score actions against explicit rules, not vague judgment
- persist adherence events for later reporting and coaching

### Primary surfaces

- coaching
- weekly reflection
- FINN report
- Mission Control
- decision review follow-up

### Data additions

Add adherence events with:

- action type
- related setup/strategy/bot
- expected rule
- actual action
- deviation type
- severity
- resolved/unresolved flag

### Exit criteria

FINN can explain:

- which rule was broken
- why it matters
- what to do to get back inside the plan

## Phase 3 - Outcome Tracking

### Goal

Connect decisions and behavior to actual results.

### Core behavior

Link reviewed decisions and adherence events to downstream outcomes and measure:

- win/loss
- return
- drawdown impact
- plan quality versus outcome quality
- repeated harmful patterns

### Output contract

- `outcome_window`
- `sample_size`
- `behavior_pattern`
- `historical_result_summary`
- `net_effect`
- `confidence_note`

### Delivery shape

- define outcome-linking policy for:
  - manual trades
  - bot decisions
  - setup-driven actions
- add delayed summarization jobs
- require sufficient evidence before FINN makes historical claims

### Required policy

- no fake causality
- low sample size must be stated explicitly
- outcomes must tie back to concrete review/adherence events

### Primary surfaces

- behavioral memory
- coaching
- weekly/monthly reports
- decision review warnings

### Exit criteria

FINN can say a pattern historically hurts or helps the user only when evidence supports it.

## Phase 4 - Portfolio Intelligence

### Goal

Move from single-item quality to portfolio-level quality.

### Core behavior

FINN determines whether a locally good action is still globally wrong because of:

- exposure concentration
- correlated setups
- overlapping bots
- budget stacking
- live risk density
- too many open decision threads

### Output contract

- `portfolio_impact`
- `exposure_delta`
- `concentration_warning`
- `stacked_risk_warning`
- `portfolio_blockers[]`
- `portfolio_safe_alternative`

### Delivery shape

- standardize one portfolio context layer for:
  - daily coach
  - Mission Control
  - decision review
  - bot review
- remove per-surface custom portfolio reasoning where possible

### Primary surfaces

- decision review
- Mission Control
- daily coach
- portfolio reports

### Exit criteria

FINN can block or down-rank a “good” trade because of portfolio reality.

## Phase 5 - Priority Engine / Mission Control 2.0

### Goal

Turn Mission Control into the daily operator queue.

### Core behavior

Rank actions by:

- portfolio impact
- urgency
- unresolved blocker weight
- decision quality
- adherence drift
- stale critical data

### Output contract

- `headline`
- `top_priorities[]`
- `review_queue[]`
- `ignore_today[]`
- `why_now`
- `suppression_reasons[]`

### Delivery shape

- keep the fast preview path
- replace flat ranking with weighted operator priority ranking
- ensure Mission Control and coaching share the same priority source of truth

### Exit criteria

Mission Control becomes a real daily operating queue instead of a summary widget.

## Phase 6 - Memory V2

### Goal

Make FINN longitudinal and personal without making it vague.

### Core behavior

Detect persistent patterns across longer windows, including:

- emotional pattern
- plan-break pattern
- exposure pattern
- recovery pattern
- hesitation pattern

### Output contract

- `memory_pattern`
- `supporting_evidence_count`
- `time_window`
- `behavioral_cost`
- `recommended_rule`
- `confidence_level`

### Memory policy

- store reusable summaries, not infinite raw replay
- summarize by evidence-backed pattern
- define explicit hygiene and retention rules

### Primary surfaces

- coaching
- behavioral memory
- weekly/monthly reports
- decision review warnings

### Exit criteria

FINN coaching becomes more personal over time without hallucinated claims.

## Phase 7 - Portfolio Operating System

### Goal

Unify the earlier phases into the actual FINN 3.0 operating layer.

### Target structure

- Portfolio
- Risk and exposure
- Bots and live decisions
- Strategies
- Setups
- Reports and outcomes
- FINN governance layer

### Delivery shape

This is primarily an integration phase:

- unify user-facing surfaces
- align shared contracts
- reduce duplicated logic
- make FINN feel like one operating layer above the product

### Exit criteria

Users experience FINN as the portfolio control plane for their trading workflow.

## Shared 3.0 Architecture

All 3.0 phases should build on shared internal subsystems rather than per-surface logic.

Target internal subsystems:

- `decision_review_engine`
- `plan_adherence_engine`
- `outcome_linking_engine`
- `portfolio_intelligence_summary`
- `priority_ranking_engine`
- `memory_summary_engine`

Preferred placement:

- keep orchestration centered in `FinnPlanService`
- extract narrower helpers only when logic becomes clearly shared and stable

## Public Interface Policy

### Phase 1 default

Do not add a broad new public API surface in the first 3.0 tranche.

Preferred rollout:

1. expose through existing FINN assistant routes and Mission Control
2. add dedicated read-only interfaces only when the UI needs them

### First direct interfaces, when needed

If direct review endpoints are added later, keep them read-only first:

- review request input
- structured review output
- no mutate/execute coupling in the same first release

## Event and Data Requirements

Before outcome tracking and Memory V2, FINN needs consistent event capture for:

- candidate action reviewed
- action approved/blocked/modified
- actual action executed or skipped
- adherence event
- outcome resolution
- portfolio snapshot around the action
- linked setup/strategy/bot ids
- asset and exposure context

Without this event layer, outcome-aware coaching will remain weak.

## Testing and Gating

### Core service tests

Add deterministic coverage for:

- decision review
  - valid trade
  - oversize risk
  - valid setup but blocked by portfolio exposure
  - insufficient context
- adherence
  - in-plan action
  - outside-plan action
  - override case
- outcome tracking
  - low sample size
  - repeated negative pattern
  - no false confidence
- portfolio intelligence
  - local-good/global-bad trade
  - stacked exposure
  - overlapping bot risk
- Mission Control 2.0
  - do-now priority
  - ignore-today suppression
  - queue ranking stability

### Replay and QA coverage

Extend the FINN promptset and release gate with 3.0 read-only cases:

- `beoordeel deze trade`
- `past dit bij mijn strategie?`
- `wijk ik af van mijn plan?`
- `waarom blokkeer je deze trade?`
- `wat is vandaag mijn hoogste prioriteit?`
- `waar verlies ik discipline?`

Do not relax any existing 2.x safety gates while adding 3.0 capability.

## Recommended Immediate 3.0 Slices

### Slice A — Review contract and storage

- define the shared structured review envelope
- add review snapshot persistence
- keep it read-only

### Slice B — Review logic MVP

- review manual trade intent
- review bot decision intent
- review setup/strategy fit

### Slice C — Adherence event model

- define explicit deviation types
- define severity ladder
- persist first adherence events

### Slice D — Mission Control priority reuse

- let Mission Control consume review/adherence outputs as ranked signals

These slices should be enough to start FINN 3.0 without waiting for all later phases.

## Final Recommendation

The right way to execute FINN 3.0 is:

1. protect the current stable baseline
2. finish the last small 2.x polish sprint
3. build decision review as the first operator-grade 3.0 layer
4. add adherence before broad personalization
5. add outcomes and portfolio intelligence before trying to feel “smarter”
6. let Mission Control become the priority engine
7. unify everything into the actual portfolio operating system

That path gives Tradamind the best chance of turning FINN from a strong assistant into a real Trading Operating System.
