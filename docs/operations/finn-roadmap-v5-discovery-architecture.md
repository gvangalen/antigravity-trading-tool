# FINN 5.0 Discovery + Architecture Plan

Last updated: 2026-06-03

## Purpose

This document defines the discovery and architecture plan for FINN 5.0.

Important:

- do not build the full 5.0 surface yet
- first decide what is safe, scalable, and structurally compatible with the current Tradamind platform
- keep FINN aligned with the existing operating principle:

`Explain -> Recommend -> Confirm -> Execute`

No autonomous financial action should bypass explicit governance.

## Current platform starting point

FINN 5.0 starts from a much stronger base than 3.0 or 4.0 did.

Current strongest references:

- FINN 3.0 full-run reference:
  - commit: `618fc35`
  - Core: `89`
  - Operator: `82`
- FINN 4.0 dedicated Performance Intelligence reference:
  - commit: `ad18bf6`
  - Performance Intelligence: `91`
  - gate-green

That matters because FINN 5.0 does not need to invent:

- review logic
- adherence logic
- outcome memory
- personal coaching
- priority ranking
- human confirmation

It needs to orchestrate and govern them.

## Current architecture in repo

### FINN orchestration layer

Current core orchestration lives in:

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

This layer already contains read-only engines for:

- decision review
- plan adherence
- outcome tracking
- portfolio intelligence
- priority engine
- portfolio operating system
- outcome memory
- personal performance
- trade journal intelligence
- personal coach

### Existing human-in-the-loop action layer

The current execution confirmation model already exists in:

- [backend/trading-tool-backend/backend/services/ai_action_engine.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_action_engine.py)

Current capabilities:

- register pending actions in `ai_pending_actions`
- enforce expiry
- execute only after explicit confirmation
- store deterministic execution result
- support replay-safe retries

This is the clearest existing FINN 5.0 foundation for:

- semi-autonomous actions
- confirmation gates
- auditability

### Existing governance and risk-event layer

The repo already contains a lightweight governance/event system:

- [backend/trading-tool-backend/backend/services/intelligence_event_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/intelligence_event_service.py)
- [backend/trading-tool-backend/backend/infrastructure/models.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/models.py)

Current event coverage already includes things like:

- drawdown alerts
- concentration risk
- duplicate strategy overlap
- volatility expansion
- macro defensive posture

Stored in:

- `ai_intelligence_events`

### Existing execution guardrails

Manual order and bot execution already contain serious guardrails:

- [backend/trading-tool-backend/backend/api/bot_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/bot_api.py)
- [backend/trading-tool-backend/backend/services/bot_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/bot_service.py)

Important current patterns:

- preflight before live manual order
- idempotency
- risk acknowledgement
- stale context blocking
- live order block audit events
- trace propagation

This is already the seed of execution governance.

### Existing portfolio state layer

Portfolio state and snapshots already exist in:

- [backend/trading-tool-backend/backend/services/portfolio_snapshot_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/portfolio_snapshot_service.py)

Current snapshot coverage:

- per-bot portfolio snapshots
- global balance snapshots
- invested capital
- unrealized PnL
- cash position

This is useful, but not yet enough for full 5.0 portfolio intelligence.

### Existing agent bootstrap + category insight layer

Repo-visible agent infrastructure already exists in:

- [backend/trading-tool-backend/backend/ai_agents/](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/ai_agents)
- [backend/trading-tool-backend/backend/services/agent_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/agent_service.py)
- [backend/trading-tool-backend/backend/api/agents_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/agents_api.py)
- [backend/trading-tool-backend/backend/celery_task/bootstrap_agents_task.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/bootstrap_agents_task.py)

This layer is currently more category-agent and insight-oriented than true multi-agent orchestration.

That is good news:

- there is reusable signal infrastructure
- but FINN 5.0 should not pretend that true agent governance already exists

## 1. Semi-autonomous actions

## Discovery outcome

FINN 5.0 should classify actions into three classes.

### A. Prepare only

These actions may be assembled, explained, and staged by FINN, but not directly executed:

- setup review
- strategy review
- portfolio review
- bot review
- risk analysis
- decision review
- performance summary
- journal lesson summary
- capital allocation recommendation

Recommended action model:

- read-only
- no confirmation required for explanation
- audit logging optional but useful for traceability
- no rollback needed

### B. Execute after confirmation

These actions are acceptable only through explicit confirmation and durable audit logging:

- create setup
- create strategy
- create bot
- activate setup
- activate bot configuration
- save trade plan
- generate report snapshot
- update risk profile
- add/remove watchlist item

These already fit the existing `AiPendingAction` pattern.

Required controls:

- explicit confirmation
- trace id
- actor identity
- TTL on approval token
- idempotency for repeat-safe execution
- execution result persistence
- rollback defined where feasible

### C. Never execute automatically

These should remain blocked from autonomous execution in 5.0:

- live trade placement without explicit preflight and confirmation
- live order placement without explicit preflight and confirmation
- large allocation changes
- portfolio-level deleveraging or concentration shifts
- strategy override that breaks plan/risk profile
- any action with insufficient context

For these, FINN may:

- explain
- recommend
- stage
- warn

But not self-execute.

## Delivery table required for implementation

For every executable action in 5.0, define:

- `action_name`
- `risk_level`
- `confirmation_required`
- `audit_logging_required`
- `rollback_supported`
- `allowed_surfaces`
- `required_context`
- `blocking_guardrails`

## 2. Portfolio intelligence

## Discovery outcome

Current portfolio support is good enough for concentration and exposure hints, but not yet deep enough for 5.0-grade portfolio intelligence.

### What FINN 5.0 must reason about

- exposure by asset
- correlated exposure
- cash buffer adequacy
- position sizing against active capital
- bot stacking
- setup clustering
- strategy overlap
- portfolio concentration
- risk density across concurrent decisions

### Data already available or partly available

- bot portfolios
- bot trade plans
- market prices
- portfolio balance snapshots
- bot portfolio snapshots
- user risk profile
- active governance events
- pending actions and execution audits

### Missing or weak data layers

- explicit correlation buckets
- portfolio concentration metrics by factor, not only symbol
- setup cluster metadata
- strategy overlap metadata
- capital at risk per open decision
- standardized portfolio conflict summary model

## Required backend inputs

### Data

- current bot positions
- symbol-level exposure
- cash available
- unrealized PnL
- active setup universe
- active strategy universe
- bot-to-strategy mapping
- bot-to-setup mapping
- risk profile
- pending execution queue

### Calculations

- concentration percentage by asset
- estimated correlated risk groups
- active capital at risk
- buffer after proposed action
- stacked exposure score
- setup cluster overlap score
- portfolio conflict severity

### APIs

Likely needed:

- read-only portfolio intelligence summary endpoint
- read-only portfolio conflict explanation endpoint
- execution-time governance summary endpoint

### Database additions

Likely needed:

- `portfolio_intelligence_snapshots`
- `portfolio_conflict_logs`
- `strategy_overlap_index`
- `setup_cluster_index`

## 3. Existing and missing AI agents

## Current agent matrix

The repo already contains these agent modules:

| Agent | Current task | Input | Output | Status | Used by FINN? | 5.0 fit |
|---|---|---|---|---|---|---|
| `macro_ai_agent` | macro category insight | macro indicators + yesterday context | category insight | active | indirectly | reusable as signal source |
| `market_ai_agent` | market category insight | global indicators + active symbols | category insight | active | indirectly | reusable as signal source |
| `technical_ai_agent` | technical category insight | technical indicators + yesterday context | category insight | active | indirectly | reusable as signal source |
| `setup_ai_agent` | setup scoring / explanation | setup config + daily scores | setup-level analysis | active | partly | reusable with governance wrappers |
| `strategy_ai_agent` | analyze existing strategies | strategies + historical context | comment + recommendation | active | partly | reusable as strategy review helper |
| `trading_bot_agent` | bot decision generation | bot config + market context + bot brain | decision + trade plan | active | yes, via bot layer | critical |
| `report_ai_agent` | daily report generation | daily platform context | report sections | active | yes | reusable |
| `weekly_report_agent` | weekly report synthesis | daily reports + scores + performance | weekly report | active | yes | reusable |
| `monthly_report_agent` | monthly reporting | report history | report | present | not central | reusable |
| `quarterly_report_agent` | quarterly reporting | report history | report | present | not central | reusable |
| `score_ai_agent` | score interpretation | score context | scoring insight | present | indirectly | reusable |

## Existing service-layer “proto-agents”

These are not file-named agents, but they are already functioning as governance/reasoning subsystems:

- `decision_review`
- `plan_adherence`
- `outcome_tracking`
- `portfolio_intelligence`
- `priority_engine`
- `outcome_memory`
- `personal_performance`
- `trade_journal_intelligence`
- `personal_coach`

These live inside [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py).

That means FINN 5.0 should prefer **agent orchestration over a stable internal governance core**, not over raw LLM workers.

## Desired 5.0 role mapping

### Risk Agent

Best current building blocks:

- `portfolio_intelligence`
- `intelligence_event_service`
- manual order preflight logic
- bot budget/risk validation

Missing:

- one canonical risk summary contract
- one canonical block / warn / allow policy

### Discipline Agent

Best current building blocks:

- `plan_adherence`
- `behavioral_intelligence`
- `outcome_memory`
- `personal_coach`

Missing:

- explicit discipline-risk severity model

### Portfolio Agent

Best current building blocks:

- `portfolio_operating_system`
- `portfolio_snapshot_service`
- `portfolio_intelligence`

Missing:

- factor-level overlap
- correlation summary
- capital conflict model

### Strategy Agent

Best current building blocks:

- `strategy_ai_agent`
- `decision_review`
- `plan_adherence`

Missing:

- strategy governance status model

### Execution Agent

Best current building blocks:

- `AiActionEngine`
- `bot_service` preflight/confirm/live-block logic
- `AiPendingAction`

Missing:

- unified execution policy registry
- confirmation policy per action type

### Performance Agent

Best current building blocks:

- `outcome_memory`
- `personal_performance`
- `trade_journal_intelligence`
- `personal_coach`

Missing:

- explicit trend-over-time and rule-formation registry

## What is missing

FINN 5.0 does **not** primarily need a dozen new agent files.

It needs:

1. a canonical orchestration contract
2. a governance policy registry
3. a clearer split between:
   - read-only intelligence
   - confirmable actions
   - forbidden actions

## 4. Execution governance

## Required governance model

Every action must be evaluated through a shared governance contract:

- `action_type`
- `subject_type`
- `subject_id`
- `risk_level`
- `context_sufficiency`
- `plan_alignment`
- `portfolio_conflict_level`
- `confirmation_required`
- `execution_allowed`
- `blocking_reason`
- `warnings`
- `audit_required`
- `rollback_mode`

## Required execution rules

### Live execution

- always requires explicit confirmation
- never direct-from-chat without preflight
- must carry trace id
- must log both approval and result

### High risk actions

- block above defined max risk
- block when context is stale or insufficient
- block when portfolio conflict severity is above threshold

### Strategy deviation

- warning required
- confirmation required
- audit required

### Insufficient context

- no execution
- explain what is missing
- offer review/preflight instead

### Portfolio conflict

- at minimum warn
- for severe conflict: block

## Audit logging requirements

Every governable action should record:

- who
- what
- why
- when
- source
- trace id
- decision route
- confirmation status
- execution result
- rollback result if applicable

## Architecture proposal

## Current situation

Today FINN works roughly like this:

user prompt  
-> assistant API routing  
-> `FinnPlanService` read-only engine or legacy assistant path  
-> optional pending action registration  
-> explicit execution via `AiActionEngine` or bot/manual order flow  

This is already a good base, but the governance policy is spread across:

- `FinnPlanService`
- `AiActionEngine`
- `bot_service`
- `intelligence_event_service`

## Desired FINN 5.0 situation

Portfolio  
-> Bots  
-> Strategies  
-> Setups  
-> Market / Macro / Technical  
-> Agents and signal sources  
-> FINN Governance Layer  
-> User

### Recommended internal shape

Introduce a dedicated FINN 5.0 governance layer with:

- `action_policy_registry`
- `agent_orchestrator`
- `portfolio_risk_summary`
- `execution_governance_service`
- `governance_audit_repository`

### Key principle

Do **not** let every agent decide execution permissions independently.

Instead:

- agents produce analysis
- governance layer decides whether the action is:
  - explain-only
  - recommend
  - confirmable
  - blocked

## Required backend changes

### New services

- `finn_action_policy_service`
- `finn_agent_orchestrator_service`
- `finn_execution_governance_service`
- `portfolio_conflict_service`
- `governance_audit_service`

### New models / tables

Likely additions:

- `finn_governance_decisions`
- `finn_action_policies`
- `portfolio_intelligence_snapshots`
- `portfolio_conflict_logs`
- `agent_orchestration_runs`

### Repositories

Likely additions:

- governance decision repository
- action policy repository
- portfolio conflict repository
- orchestration run repository

### Workflows

- explain-only decision workflow
- recommend workflow
- confirmable action workflow
- blocked-action workflow
- rollback workflow for reversible actions

## Required frontend changes

### New panels

- governance decision panel
- confirmation sheet
- blocked-action explanation panel
- portfolio conflict panel
- orchestration trace panel for operator/debug mode

### New explain/review surfaces

- action review before confirmation
- why FINN recommends this
- why FINN blocks this
- what changed since last review

## Required database changes

Beyond current 3.0 / 4.0 layers, 5.0 likely needs:

- durable decision history
- governance logs
- orchestration runs
- action approval state
- portfolio conflict state
- execution trail links

Likely schema areas:

- outcome memory history
- performance history
- decision history
- governance logs
- portfolio intelligence snapshots

## QA strategy

## Core QA

Keep the existing FINN Core QA unchanged.

It still protects:

- conversation
- education
- product explain
- context
- coaching
- reliability

## Operator QA

Keep the existing Operator QA unchanged.

It still protects:

- decision review
- plan adherence
- outcome tracking
- portfolio intelligence
- priority engine

## New FINN 5.0 QA categories

### Decision Quality

- does FINN produce better governed action recommendations?

### Portfolio Intelligence

- does FINN understand total portfolio pressure and conflict?

### Governance

- does FINN obey safety rules consistently?

### Agent Orchestration

- does FINN call the right agent or subsystem for the problem?

### Semi-autonomous Actions

- does FINN execute only what is allowed?

## Risk analysis

### Technical risks

- orchestration complexity creates hidden latency
- duplicated policy logic across assistant, bot, and governance layers
- stale context causes bad execution recommendations

### UX risks

- too many warnings create fatigue
- too many confirmations create friction
- blocked actions may feel arbitrary if explanation quality is weak

### Governance risks

- inconsistent allow/block rules across surfaces
- agent recommendations bypassing portfolio conflict checks
- human confirmation tokens reused incorrectly

### Safety risks

- accidental live order execution path expansion
- high-risk allocation mutation without enough friction
- autonomy leaking into low-context environments

### Operational risks

- replay flakiness from heavy orchestration
- hard-to-debug action traces
- brittle coupling to external exchange state

## Phased build plan

## FINN 5.0A — Highest ROI

Focus:

- action policy registry
- governance decision model
- portfolio conflict summary
- orchestration over existing internal engines

Why:

- highest safety leverage
- most reuse of current 3.0/4.0 layers
- enables explain/recommend/confirm cleanly

### Recommended first slice

Build a read-only **Governed Action Review** layer:

- user asks FINN to perform or prepare an action
- FINN returns:
  - allowed?
  - needs confirmation?
  - blocked?
  - why?
  - what context is missing?

No new autonomous execution yet.

## FINN 5.0B — Medium impact

Focus:

- confirmable action expansion through `AiPendingAction`
- portfolio-aware action preparation
- orchestration trace visibility
- policy-backed bot and strategy mutations

## FINN 5.0C — Advanced features

Focus:

- semi-autonomous non-financial actions
- richer multi-agent task delegation
- reversible workflow execution
- deeper execution governance

## What not to build yet

Explicitly do **not** build yet:

- direct autonomous live trades
- autonomous large allocation rebalances
- self-directed risk profile changes without confirmation
- free-form multi-step agent execution without policy registry
- personal AI agents with execution rights

These are too early because:

- governance policy is not yet centralized
- portfolio conflict logic is not yet deep enough
- audit and rollback models are not yet complete

## Final advice

### 1. What is the highest ROI for FINN 5.0?

The highest ROI is **not** autonomous execution.

It is:

- a shared governance layer
- portfolio conflict reasoning
- action policy classification above existing FINN 3.0 and 4.0 engines

### 2. Which first slice should be built?

Build:

- **Governed Action Review**

That means:

- classify an intended action
- evaluate risk, context, plan fit, and portfolio fit
- return:
  - explain
  - recommend
  - confirm
  - block

without broad new autonomy.

### 3. Which existing components can be reused?

Strong reuse candidates:

- `FinnPlanService`
- `AiActionEngine`
- `bot_service` preflight/guardrails
- `intelligence_event_service`
- `portfolio_snapshot_service`
- `trading_bot_agent`
- `strategy_ai_agent`
- existing category agents
- `AiPendingAction`
- `AiIntelligenceEvent`

### 4. What must be proven before further automation is responsible?

Before more automation is allowed, prove:

- portfolio conflict reasoning is trustworthy
- action policy decisions are consistent across surfaces
- execution audit is complete
- confirmation and rollback models are durable
- orchestration stays within latency budgets

## Short version

FINN 5.0 should not begin as “more autonomous FINN”.

It should begin as:

- governed action preparation
- portfolio-aware action approval
- explicit orchestration over existing review, performance, and execution layers

That is the safest and highest-ROI path to a real Trading Operating Layer.

## Execution reference

- [FINN 5.0A Engineering Checklist](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-5a-governed-action-review-checklist.md)
