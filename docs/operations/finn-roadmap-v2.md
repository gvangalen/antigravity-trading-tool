# FINN Roadmap V2

Last updated: 2026-05-30

## Purpose

This document turns the current FINN capability audit into a concrete V2 roadmap for Tradamind.

The goal of FINN V2 is not just to make the assistant smarter in isolation. The goal is to make FINN a reliable trading operator layer that:

- understands the user's real working context
- uses Tradamind data and tools consistently
- remembers enough to coach over time
- helps users act safely
- stays fast and predictable in production

## QA Reality Check

The capability audit and the live QA audit tell two different but compatible truths:

1. FINN already has substantial backend capability.
2. FINN is still not reliable enough as a broad first-time assistant experience.

The strongest current gap is not raw backend power. The strongest gap is core assistant experience:

- routing drift
- session-state contamination
- weak educational fallback
- weak explain-first behavior for general questions
- inconsistent page and entity awareness in real user flows

That means FINN V2 should not start by adding more intelligence layers first. It should start by making the existing intelligence usable, predictable, and understandable for real users.

## Current Baseline

FINN today is already strong in five areas:

1. context-aware assistant behavior
2. portfolio and behavioral coaching
3. Mission Control orchestration
4. decision explain / review flows
5. operator follow-through flows

FINN today is still limited in five areas:

1. long-term memory depth
2. unified architecture
3. broad tool-use across the full product
4. outcome-aware personalization
5. predictable performance on heavy operator surfaces

## V2 Product Goal

FINN V2 should become:

- the user's operational trading copilot
- the control layer above setups, strategies, bots, reports, and portfolio monitoring
- a durable coaching system that gets more useful over time
- a safer execution gate for real operator workflows

## Guiding Principles

### 1. Deterministic where safety matters

Execution, risk gating, operator resolutions, and mission routing should stay deterministic and auditable.

### 2. AI where synthesis matters

Reflection, explanation, summarization, personalization, and strategy-level synthesis can be more model-driven.

### 3. One FINN surface, one FINN brain

Users should experience one FINN, even if the backend still contains multiple services. V2 should reduce architectural split-brain over time.

### 4. Advice must connect to action

Every strong FINN insight should ideally lead to:

- a follow-up action
- a safe deferral path
- a reasoned suppression
- or a documented resolution

### 5. Reliability is part of capability

If a feature is smart but slow, flaky, or inconsistent across surfaces, it is not complete.

## Current Capability Snapshot

| Domain | Current State | V2 Direction |
| --- | --- | --- |
| Context awareness | Strong page/asset/setup/bot context | richer strategy and portfolio context inheritance |
| Data access | Broad coverage across scores, market, technical, bots, reports, portfolio | unify data contracts and reduce request fan-out |
| Actions | Good on bot/strategy/mission flows | expand into watchlist, setup lifecycle, richer portfolio actions |
| Memory | conversation + preferences + activity-derived memory | durable long-term user memory and outcome memory |
| Coaching | one of FINN's strongest layers | make more personalized, longitudinal, and outcome-aware |
| Architecture | hybrid FINN + legacy assistant stack | move toward one orchestration layer |
| Reliability | much improved, but still uneven on heavy surfaces | predictable deploys, stable startup, lower latency |

## Roadmap Structure

FINN V2 is split into seven phases. Each phase is intended to be complete enough to ship and validate.

## Status Snapshot

- **Phase 0 - FINN Core Experience Hardening:** functionally complete
- **Phase 1 - Unified FINN Core:** now started with a first legacy fallback reduction layer at the API boundary

That means FINN V2 no longer starts from “capability first”. It now starts from a hardened core assistant experience and a gradual reduction of legacy split-brain behavior.

## Phase 0 - FINN Core Experience Hardening

### Goal

Make FINN reliable as a first-line assistant before expanding deeper capabilities.

### Why this phase matters

Recent live QA showed that FINN is often stronger as a specialist operator engine than as a general assistant experience. That is the wrong order for user trust.

Examples of current failure modes:

- general questions fall into irrelevant toolflows
- coaching prompts can route into strategy or bot creation
- educational prompts fail with generic error responses
- older draft/session state can hijack the current turn
- entity/page awareness is not reliable enough under real user movement

### Scope

- harden intent routing
- isolate session state and old drafts more strictly
- build an explicit educational fallback layer
- separate explain-first mode from create/update/execute mode
- tighten context awareness for:
  - page
  - asset
  - setup
  - strategy
  - bot
  - report
- reduce multi-turn drift

### Deliverables

- strict routing policy between:
  - general assistant
  - coaching
  - explain
  - create/update
  - execute
- session-state contamination guards
- explicit “education mode” with safe fallback content for:
  - RSI
  - MA200
  - Wyckoff
  - risk management
  - DCA
  - stop loss
  - position sizing
- explain-first handling for product questions such as:
  - setup uitleg
  - strategie uitleg
  - bot uitleg
  - rapport uitleg
- context confidence rules and fallbacks
- first-time user regression pack

### Success criteria

- ordinary assistant questions no longer default into bot or strategy flows
- educational prompts no longer return generic “Kon geen analyse ophalen” failures
- coaching prompts stay in coaching unless the user explicitly asks to build or execute
- active entity awareness is correct often enough to trust in normal use
- multi-turn sessions do not drift into stale draft behavior after a few turns

## Phase 1 - Unified FINN Core

### Goal

Reduce architectural split between deterministic FINN flows and the older assistant orchestration paths.

### Why this phase matters

Right now FINN is powerful, but the system still has multiple brains:

- `FinnPlanService`
- `AiAssistantService`
- background domain agents

That makes behavior harder to reason about, harder to extend, and easier to regress.

### Scope

- define one canonical FINN request contract
- move more routing authority into the FINN layer
- reduce duplicate intent/context handling
- standardize assistant state persistence
- standardize assistant response envelopes across:
  - chat
  - mission control
  - reports
  - follow-through
- add deterministic rescue when the legacy assistant returns a generic failure or a clearly wrong transactional flow for a non-transactional prompt

### Deliverables

- single FINN orchestration contract
- de-duplicated context hydration path
- de-duplicated intent routing for core FINN flows
- common response schema conventions
- migration map for legacy assistant behavior
- legacy fallback reduction layer so that generic legacy failures are replaced by deterministic FINN responses where possible

### Success criteria

- core FINN flows do not depend on parallel legacy routing logic
- assistant responses are structurally consistent across surfaces
- fewer request-path branches for equivalent user intents

## Phase 2 - Memory V2

### Goal

Give FINN real user memory, not just session state and recent activity.

### Why this phase matters

Today FINN remembers enough to be context-aware and behavior-aware, but not enough to become deeply personal over time.

### Scope

- long-term user memory profile
- outcome memory tied to:
  - setups
  - strategies
  - bot decisions
  - operator actions
- regime memory for recurring behavior patterns
- preference evolution over time
- memory summaries that can be safely reused without replaying full histories

### Memory layers to build

1. conversational memory
2. operator memory
3. behavioral memory
4. outcome memory
5. preference memory

### Deliverables

- durable user memory store
- memory summarization jobs
- memory retrieval policy for FINN prompts and deterministic flows
- explicit memory hygiene and retention rules

### Success criteria

- FINN can explain not only what is happening now, but what repeatedly happens for this user
- FINN can reference historical behavior and outcomes in a grounded way
- coaching gets better over multiple weeks, not just one session

## Phase 3 - Tool Use Expansion

### Goal

Expand FINN from a strong advisor into a broader product operator.

### Why this phase matters

FINN already handles some actions well, especially around bots and Mission Control. V2 should close the gap between insight and execution across more product areas.

### Scope

- watchlist actions
- richer setup lifecycle actions
- richer strategy lifecycle actions
- portfolio curation actions
- report follow-up actions
- safer batched operator actions where appropriate

### Target action families

- create
- update
- resolve
- snooze
- monitor
- suppress
- regenerate
- compare
- archive

### Deliverables

- expanded server-issued action catalog
- action permission model
- action audit coverage
- clearer UI treatment for reversible vs irreversible actions

### Success criteria

- users can complete more workflows from FINN without dropping into raw product navigation
- each action has a clear audit trail and safe follow-through
- action scope is consistent with user permissions and risk profile

## Phase 4 - Coaching & Behavioral Intelligence V2

### Goal

Turn FINN from a clever commentator into a real long-horizon trading coach.

### Why this phase matters

Current coaching is already one of the strongest parts of FINN. V2 should make it more longitudinal, more personal, and more outcome-aware.

### Scope

- stronger adherence coaching
- repeat-pattern detection
- bias detection:
  - FOMO
  - overtrading
  - revenge behavior
  - hesitation under review pressure
- link behavior to outcomes over time
- richer “what changed since last week” coaching
- coaching plans, not just coaching observations

### Deliverables

- behavioral scorecards over time
- deviation severity ladder
- personal coaching playbooks
- outcome-linked coaching summaries
- richer behavioral blocks in reports and Mission Control

### Success criteria

- FINN can show recurring strengths and recurring mistakes over time
- coaching is individualized rather than generic
- users can see what habits are actually costing them quality

## Phase 5 - Portfolio Operating System

### Goal

Make FINN the portfolio-level control plane above individual setups and bots.

### Why this phase matters

Tradamind is moving toward an AI-native trading operating system. That means FINN should help govern the whole portfolio, not just explain single items.

### Scope

- capital crowding detection
- cross-bot conflict management
- correlated risk surfacing
- queue prioritization by portfolio importance
- portfolio-level “do not touch today” lanes
- execution sequencing advice
- stronger multi-asset operator planning

### Deliverables

- portfolio action planner
- exposure and crowding heuristics
- sequencing recommendations
- portfolio-level operator dashboards
- richer Mission Control priorities rooted in portfolio impact

### Success criteria

- FINN can explain not just whether one item is risky, but what matters most across the whole book
- Mission Control reflects true portfolio priorities, not just item recency
- users can act on fewer, better-chosen tasks

## Phase 6 - Reliability, Performance, and Production Readiness

### Goal

Make FINN feel operationally trustworthy in real daily use.

### Why this phase matters

A system that is insightful but slow, inconsistent, or rollout-fragile will not feel dependable to users.

### Scope

- Mission Control latency reduction
- startup and deploy stability
- cache consistency across surfaces
- stronger marker discipline and rollout observability
- background load isolation
- degrade-gracefully rules for non-critical dependencies

### Deliverables

- target latency budget for:
  - chat
  - mission control
  - reports
  - action execute
- deploy gates and rollback discipline
- surface consistency checks
- health and freshness diagnostics for FINN-specific surfaces

### Success criteria

- Mission Control response time becomes predictable enough for daily operator use
- deploys no longer leave ambiguous “live code vs marker” states
- user-facing FINN surfaces degrade gracefully rather than failing noisily

## Priority Order

Recommended implementation order:

1. Phase 0 - FINN Core Experience Hardening
2. Phase 1 - Unified FINN Core
3. Phase 2 - Memory V2
4. Phase 6 - Reliability, Performance, and Production Readiness
5. Phase 3 - Tool Use Expansion
6. Phase 4 - Coaching & Behavioral Intelligence V2
7. Phase 5 - Portfolio Operating System

## Why this order

- Core experience hardening prevents user trust from breaking before deeper capability matters.
- Unified architecture makes later work safer.
- Memory increases the quality of almost every later layer.
- Reliability work prevents advanced features from feeling fragile.
- Tool use should expand after the core and runtime are stable enough.
- Portfolio OS should come after memory, coaching, and action rails are mature enough to support it.

## What Counts As “Done” For V2

FINN V2 is not done when it has more prompts.

FINN V2 is done when:

- context is rich and consistent
- memory improves over time
- insights consistently connect to actions
- coaching becomes outcome-aware
- portfolio priorities are explicit
- execution remains safe
- the runtime is stable enough for daily trust

## Recommended Immediate Next Work

If we start V2 now, the first implementation slices should be:

### Slice A - Core routing hardening

- map every active FINN route to one of:
  - general assistant
  - coaching
  - explain
  - create/update
  - execute
- add stronger routing tests for:
  - ordinary questions
  - educational questions
  - emotional/coaching prompts
  - product explanation prompts
- remove obvious cross-mode drift into `strategy_creation` / `bot_creation`

### Slice B - Session-state isolation

- define strict rules for when old `finn_draft` may influence a new turn
- add explicit reset/clear semantics
- block stale draft reuse when the new prompt is clearly explanatory or educational
- add regression coverage for multi-turn contamination

### Slice C - Education and explain-first fallback

- add safe educational fallback content for the highest-frequency trading concepts
- ensure product explanation prompts prefer explain mode over transactional mode
- define minimum “first user” answer quality for:
  - “wat is RSI”
  - “wat is een trading plan”
  - “wanneer doe ik beter niets”
  - “leg mijn setup/strategie/bot uit”

### Slice D - Context confidence model

- score confidence for page/entity context
- if confidence is weak, ask or narrow instead of acting
- prevent wrong-entity explanations when multiple drafts or entities exist

### Slice E - Mission Control performance baseline

- record current live latency ranges
- instrument substep timings
- identify top blocking reads
- set target SLO for `GET /api/assistant/mission-control`

## P0 / P1 / P2 Backlog

### P0 - Must fix before broad FINN trust

1. Router hardening across:
   - general questions
   - coaching
   - product explanation
   - create/update
   - execute
2. Session-state isolation and stale draft containment
3. Educational fallback for basic trading concepts
4. Explain-first mode for setup, strategy, bot, and report questions
5. Stronger page/entity awareness
6. Multi-turn drift reduction

### P1 - High-value follow-up after P0

1. Unified FINN orchestration convergence
2. Tool gating refinement
3. Better product explanation quality per entity type
4. Mission Control latency reduction
5. Better observability for routing mistakes and context confidence
6. Stress-session consistency improvements

### P2 - Deeper platform and product expansion

1. Memory V2
2. Outcome-linked coaching
3. Broader tool use expansion
4. Portfolio Operating System layer
5. Advanced personalization
6. Richer autonomous operating patterns under guardrails

## Risks

### Architectural drift

If V2 features are added without convergence, FINN becomes smarter but harder to trust and maintain.

### Prompt-first overreach

If too much logic moves into freeform model behavior, execution and safety quality will regress.

### Surface inconsistency

If chat, Mission Control, and reports each evolve their own response contracts, FINN will feel fragmented.

### Reliability debt

If latency and deploy/runtime stability are not treated as first-class work, user trust will cap out before product capability does.

## Suggested Ownership Split

### Product / UX

- define operator journeys
- define coaching surfaces
- define action semantics
- define user-facing memory and trust boundaries

### Backend / Platform

- unify orchestration
- build memory storage and retrieval
- stabilize deploy/runtime
- improve Mission Control performance

### AI / Prompting

- behavioral summarization
- memory distillation
- explain layer quality
- coaching tone and intervention strategy

## Final Recommendation

Tradamind should treat FINN V2 as a platform roadmap, not a loose feature backlog.

The smartest next move is:

1. harden the core FINN user experience
2. converge the FINN core architecture
3. build durable memory
4. harden runtime reliability
5. then expand autonomous tool-use and portfolio-level control

That sequence gives Tradamind the best chance of turning FINN into a real AI-native trading operating system layer instead of a growing collection of clever but uneven assistant features.
