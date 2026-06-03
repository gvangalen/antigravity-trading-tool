# FINN 5.0A Engineering Checklist

Last updated: 2026-06-03

## Goal

Build the first FINN 5.0 slice as a **Governed Action Review** layer.

This slice should let FINN evaluate an intended action and answer:

- is this action allowed?
- does it need confirmation?
- should it be blocked?
- why?
- what context is missing?

This is intentionally:

- read-only first
- governance-first
- built on top of existing 3.0 and 4.0 logic

## Definition of done

FINN 5.0A is done when:

1. FINN can review an intended action through a single governance contract
2. the result clearly returns:
   - `explain`
   - `recommend`
   - `confirm`
   - or `block`
3. no new autonomous financial execution path is introduced
4. existing action confirmation and execution stay behind the current explicit gates

## Target contract

Every governed action review should produce:

- `action_type`
- `subject_type`
- `subject_id`
- `risk_level`
- `context_sufficiency`
- `plan_alignment`
- `portfolio_conflict_level`
- `confirmation_required`
- `execution_allowed`
- `governance_status`
- `blocking_reason`
- `warnings`
- `recommended_next_step`
- `audit_required`
- `rollback_mode`

## Build order

1. governance contract
2. action policy registry
3. governed action review builder in FINN
4. API exposure
5. tests
6. optional first productsurface after backend slice is stable

## File-by-file checklist

### 1. [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)

Primary work:

- add `looks_like_governed_action_review_request(...)`
- add `build_governed_action_review_response(...)`
- reuse existing engines instead of duplicating judgment:
  - `build_decision_review_response(...)`
  - `build_plan_adherence_review_response(...)`
  - `build_portfolio_intelligence_response(...)`
  - `build_portfolio_operating_system_response(...)`
  - `build_personal_performance_response(...)` where relevant

Implementation tasks:

- normalize intended action from prompt + context
- detect action families such as:
  - create setup
  - create strategy
  - create bot
  - activate setup
  - activate bot
  - save trade plan
  - live manual order
  - portfolio mutation
- produce one canonical governance payload
- determine:
  - `governance_status = explain | recommend | confirm | block`
  - `execution_allowed`
  - `confirmation_required`
- avoid execution side effects in this slice

Acceptance:

- prompt examples like:
  - `Mag FINN deze strategie activeren?`
  - `Kun je deze bot voor me klaarzetten?`
  - `Mag dit live uitgevoerd worden?`
  - `Waarom blokkeer je deze actie?`
  route to a new governed review lane

### 2. New service: `backend/trading-tool-backend/backend/services/finn_action_policy_service.py`

Primary work:

- introduce a small policy registry service

First responsibilities:

- define action classes:
  - `prepare_only`
  - `confirm_required`
  - `never_auto_execute`
- define per-action defaults:
  - risk level
  - audit required
  - rollback mode
  - minimum context requirements

Initial action registry:

- `setup_review`
- `strategy_review`
- `portfolio_review`
- `bot_review`
- `decision_review`
- `create_setup`
- `create_strategy`
- `create_bot`
- `activate_setup`
- `activate_bot`
- `save_trade_plan`
- `update_risk_profile`
- `watchlist_add`
- `watchlist_remove`
- `live_manual_order`
- `portfolio_rebalance`

Acceptance:

- every governed action review can ask this service for baseline policy
- action rules are not hardcoded all over the place

### 3. New service: `backend/trading-tool-backend/backend/services/finn_execution_governance_service.py`

Primary work:

- centralize governance evaluation

Responsibilities:

- combine:
  - action policy
  - context sufficiency
  - plan alignment
  - portfolio conflict
  - explicit execution sensitivity
- return the final governance decision object

Rules for first slice:

- insufficient context -> `block`
- live trade / live order -> at least `confirm`, often `block` if context stale
- portfolio conflict severe -> `block`
- plan deviation moderate/high -> `warn` or `confirm`

Acceptance:

- business rules live in one place
- FINN, bot preflight, and future UI surfaces can reuse the same evaluation

### 4. [backend/trading-tool-backend/backend/services/ai_action_engine.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_action_engine.py)

Primary work:

- do not expand execution authority yet
- prepare the engine to accept governance metadata in pending actions

Implementation tasks:

- allow pending action payloads to carry:
  - governance snapshot
  - policy class
  - confirmation rationale
  - rollback mode
- keep current explicit confirmation and expiry behavior unchanged

Acceptance:

- action registration can preserve governance context for later audit
- no direct autonomous execution is introduced

### 5. [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

Primary work:

- add routing for `governed_action_review`
- place it carefully near other non-transactional governed flows

Implementation tasks:

- route explicit governance prompts to the new FINN builder
- ensure rescue envelope can still recover to this lane
- keep transactional execution endpoints unchanged

Acceptance:

- governed review prompts do not fall into generic help
- governed review does not bypass existing execution APIs

### 6. [backend/trading-tool-backend/backend/services/bot_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/bot_service.py)

Primary work:

- reuse 5.0A governance evaluation inside preflight-capable order and bot flows

Implementation tasks:

- expose current preflight context in a form the governance service can reuse
- do not duplicate portfolio/risk reasoning if it already exists here
- keep:
  - manual order preflight
  - manual order block audit
  - idempotency
  - stale context blocks

Acceptance:

- 5.0A governance output for execution-sensitive actions agrees with current bot guardrails

### 7. [backend/trading-tool-backend/backend/services/intelligence_event_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/intelligence_event_service.py)

Primary work:

- define whether governed reviews should emit lightweight audit/governance events

First safe scope:

- log only important blocked or high-risk governed reviews
- avoid noisy event spam for every harmless explain request

Acceptance:

- severe governance conflicts can become visible to Mission Control later
- no alert flood

### 8. [backend/trading-tool-backend/backend/infrastructure/models.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/models.py)

Primary work:

- phase 5.0A should prefer minimal schema change

Recommended first change:

- do not add broad new tables before the contract settles
- if needed, add one narrow model later for durable governance decisions:
  - `FinnGovernanceDecision`

For 5.0A MVP:

- prefer embedding governance snapshot into existing `ai_pending_actions.payload`
- optionally reuse `ai_intelligence_events` for blocked/high-risk audit summaries

Acceptance:

- avoid premature schema sprawl
- keep first slice lightweight

### 9. Optional new migration

If a dedicated governance table becomes necessary after the MVP contract stabilizes:

- add migration for:
  - `finn_governance_decisions`

Suggested fields:

- `id`
- `user_id`
- `action_type`
- `subject_type`
- `subject_id`
- `governance_status`
- `risk_level`
- `context_sufficiency`
- `plan_alignment`
- `portfolio_conflict_level`
- `confirmation_required`
- `execution_allowed`
- `blocking_reason`
- `warnings`
- `policy_snapshot`
- `trace_id`
- `created_at`

For now:

- keep this as phase 5.0A optional, not mandatory

### 10. Tests

#### [backend/trading-tool-backend/backend/tests/test_finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_finn_plan_service.py)

Add:

- governed review detector tests
- governed review contract tests
- action-class coverage tests:
  - prepare only
  - confirm required
  - block

Prompt examples:

- `Mag FINN deze setup activeren?`
- `Mag deze bot nu live draaien?`
- `Kun je deze strategie voor me aanmaken?`
- `Waarom blokkeer je deze live order?`

#### [backend/trading-tool-backend/backend/tests/test_ai_assistant_api_unified_core.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_ai_assistant_api_unified_core.py)

Add:

- rescue envelope prefers governed action review for governance prompts
- governed review does not fall through to generic help

#### [backend/trading-tool-backend/backend/tests/test_finn_qa_replay_gate.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_finn_qa_replay_gate.py)

Add:

- first 5.0A replay assertions once promptset exists

### 11. QA artifacts

Create:

- `docs/operations/finn-5-governance-qa.md`
- `docs/operations/finn-qa-promptset-governance.json`

First categories:

- governed review routing
- confirmation classification
- execution block safety
- portfolio conflict governance
- insufficient context blocking

## First prompts to validate

- `Mag FINN deze strategie activeren?`
- `Kan FINN deze bot voor me aanmaken?`
- `Mag dit direct live uitgevoerd worden?`
- `Welke bevestiging is hiervoor nodig?`
- `Waarom blokkeer je deze actie?`
- `Welke context mist nog voor uitvoering?`

## Minimal delivery recommendation

For the first PR / tranche:

1. add action policy service
2. add execution governance service
3. add governed action review response in `FinnPlanService`
4. route it in `ai_assistant_api.py`
5. add targeted tests

Do not yet:

- create broad new UI
- add autonomous execution
- expand live trading authority
- add a large migration set unless the contract proves stable

## Highest ROI slice

The highest ROI 5.0A slice is:

- a read-only governed action review over existing FINN intelligence

That gives us:

- safer architecture
- explicit policy thinking
- reusable governance outputs
- a clean bridge into later confirmable actions
