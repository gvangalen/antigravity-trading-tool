# FINN P0 Root Cause & Instrumentation Audit

Last updated: 2026-05-30

## Purpose

This document explains where the current FINN P0 failures most likely originate before larger fixes are implemented.

It is intentionally diagnostic first:

- instrument the current system
- identify where routing, context, and draft reuse go wrong
- prioritize fixes by impact and difficulty

This is not the full remediation plan. It is the root-cause baseline for the remediation plan.

## What Was Instrumented

Structured prompt audit logging was added in:

- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)

The log event prefix is:

- `📋 [FINN-P0-AUDIT]`

For each prompt, the audit now logs:

- prompt
- detected intent
- intent confidence
- selected flow
- selected entity
- used context:
  - page
  - page_type
  - symbol
  - timeframe
  - setup_id
  - strategy_id
  - bot_id
- whether a draft was used
- draft summary
- response type
- success label
- route source:
  - `finn`
  - `finn_stream`
  - `legacy_assistant`
  - `exception`

## Measured Live Sample

After the instrumentation rollout, a controlled live promptset was run against production with real authenticated context. The first measured sample showed a strong stale-draft failure mode:

- `Hoi FINN, wat kun je voor mij doen?` -> `bot_creation`
- `Wat is RSI in simpele taal?` -> `bot_creation`
- `Wat is DCA?` -> `bot_creation`
- `Welke strategie bekijk ik nu?` -> `bot_creation`
- `Leg mijn setup uit` -> `bot_creation`
- `Ik voel FOMO, wat moet ik doen?` -> `bot_creation`

The audit logs showed the same pattern:

- `draft_used = true`
- `draft_kind = bot`
- stale draft carried `asset = ETH`, `strategy_id = 257`, `existing_bot_id = 130`
- route source stayed inside deterministic FINN, but the stale transactional draft won almost every turn

This turned the main P0 hypothesis into a measured fact:

- **stale transactional draft reuse was the primary front-door routing bug**

After the first routing/state-isolation fix, a second live sample showed:

- `Hoi FINN, wat kun je voor mij doen?` -> `general_help`
- `Wat is RSI in simpele taal?` -> `education`
- `Wat is DCA?` -> `education`
- `Maak een wekelijkse BTC setup voor een breakout long` -> `plan_creation`

That confirmed the first P0 fix direction was correct.

The same second sample also exposed the next concrete gaps:

- `Welke strategie bekijk ik nu?` hit a deterministic explain path but failed on a missing import (`StrategyRepository`)
- `Leg mijn setup uit` still slipped into the legacy assistant path
- `Ik voel FOMO, wat moet ik doen?` still slipped into the legacy assistant path
- those legacy fallbacks then degraded because live OpenAI quota returned `429 insufficient_quota`

So the measured sequence was:

1. stale draft hijack dominated the first sample
2. after isolating drafts, the remaining failures became much narrower:
   - explain-path coverage
   - coaching detection
   - legacy fallback quota sensitivity

After the explain/coaching routing tranche was deployed, a third live sample on production showed the narrower cases now routing correctly as deterministic FINN responses instead of falling into create/update or legacy fallback:

- `Welke strategie bekijk ik nu?` -> `context_explain`
- `Leg mijn setup uit` -> `context_explain`
- `Ik voel FOMO, wat moet ik doen?` -> `behavioral_intelligence`
- `Maak een wekelijkse BTC setup voor een breakout long` -> `plan_creation`

The corresponding audit logs confirmed the intended shape:

- `draft_used = false` for strategy explain
- `draft_used = false` for setup explain
- `draft_used = false` for coaching
- `draft_used = true` only for the explicitly transactional setup-building turn

That means the first measured P0 hardening result is now clear:

- **general/help, education, explain, coaching, and transactional setup creation are no longer being front-door hijacked by stale transactional drafts in the measured live sample**

After that, a first **Unified FINN Core / legacy fallback reduction** pass was added at the API boundary:

- if the legacy assistant returns a generic failure such as `Kon geen analyse ophalen`
- or if a non-transactional prompt still comes back in a legacy transactional flow like `bot_creation`
- the API now rescues that turn back into a deterministic FINN response before returning it to the user

That rescue layer now prefers deterministic FINN envelopes for:

- general help
- education
- explain
- behavioral coaching
- weekly reflection
- behavioral memory
- Finn reports
- daily coach
- status
- indicator insight

This matters because it reduces how often:

- OpenAI quota issues
- coarse legacy intent classification
- or stale legacy flow state

can leak through as the visible first-line FINN experience.

After the broader explain-first entity tranche and the new multi-turn regression pack were added, a fresh live sequence on production also held up across mixed prompt types in one run:

- `Hoi FINN, wat kun je voor mij doen?` -> `general_help`
- `Wat is RSI in simpele taal?` -> `education`
- `Maak een wekelijkse BTC setup voor een breakout long` -> `plan_creation`
- `Ik voel FOMO, wat moet ik doen?` -> `behavioral_intelligence`
- `Welke strategie bekijk ik nu?` -> `context_explain`
- `Leg mijn setup uit` -> `context_explain`
- `Welke score zie ik nu?` -> `context_explain`
- `Leg mijn bot uit` -> `context_explain`

This matters because it is the first measured sequence that mixes:

- general help
- education
- transactional creation
- coaching
- setup/strategy explain
- score explain
- bot explain

without drifting back into `bot_creation` or `strategy_creation` for the non-transactional turns.

## Root Cause Summary

The current QA failures are not caused by one bug. They are caused by five interacting issues:

1. routing classes overlap too much
2. transactional drafts persist too aggressively across turns
3. explain and education intents do not have their own strong first-class path
4. context is available, but not confidence-scored
5. the legacy fallback path degrades into generic “analysis failed” output too easily

## Current P0 Status

As of the latest measured tranche:

- **Phase 0 is functionally complete**
- the biggest front-door routing failures are now covered by:
  - stale draft isolation
  - stronger non-transactional routing
  - explicit education handling
  - explain-first entity handling
  - context confidence
  - multi-turn drift regressions

The next layer is no longer “find the root cause”. It is:

- reduce dependence on the legacy assistant path
- keep deterministic FINN responses as the primary user-facing brain

## Detailed Findings

### 1. Educational questions fail

#### Problem

Basic questions like RSI, MA200, Wyckoff, DCA, stop loss, and risk management often end in:

- `⚠️ Kon geen analyse ophalen. Probeer opnieuw.`

#### Most likely cause

There is no dedicated educational mode in the FINN deterministic routing layer.

So these questions often bypass the deterministic FINN routes and fall into the older assistant path. In that path:

- `_classify_intent()` is coarse
- educational questions are not modeled as a first-class domain
- the JSON-mode assistant fallback can return no usable response
- the default user-facing fallback becomes “Kon geen analyse ophalen”

#### Where it originates

- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
  - `_classify_intent()`
  - JSON-mode fallback handling
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)
  - routing falls through to legacy assistant when no deterministic FINN route matches

#### Expected QA impact

Very high.

This directly hurts:

- first-time user trust
- general assistant score
- trading knowledge score

#### Fix difficulty

Medium.

The logic is conceptually straightforward, but should be implemented carefully because it changes the front door of the assistant.

### 2. Prompts fall back into `bot_creation` or `strategy_creation`

#### Problem

Questions that should explain or coach sometimes route into:

- `bot_creation`
- `strategy_creation`

#### Most likely cause

The transactional matchers are too permissive.

Examples:

- `looks_like_strategy_request()`
- `looks_like_bot_request()`
- `looks_like_plan_request()`

They can match on broad combinations of:

- one domain word
- one create/update intent word
- or a carried context reference

At the same time, old drafts are hydrated automatically and were historically allowed to bias new turns too easily.

#### Where it originates

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
  - `looks_like_plan_request()`
  - `looks_like_strategy_request()`
  - `looks_like_bot_request()`
  - `hydrate_context()`
- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
  - deterministic pre-parser and chain-of-dependence redirects

#### Expected QA impact

Very high.

This directly harms:

- context awareness score
- tool usage score
- coaching score
- overall consistency score

#### Fix difficulty

Low to medium.

The root problem is understandable, but the fix has to be regression-tested carefully because these are central routing gates.

### 3. Old drafts influence new prompts

#### Problem

Users ask a new question, but FINN behaves as if they are still in an earlier setup/strategy/bot flow.

#### Most likely cause

Draft reuse is too eager.

`hydrate_context()` loads transactional drafts from `conversation_state` whenever `current_flow` is transactional. Historically, downstream matchers were then willing to continue that draft with very weak evidence.

That means:

- stale flowstate remains active
- new prompts are interpreted as slot-fill or continuation
- explanatory or educational questions can be absorbed into old transactional context

#### Where it originates

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
  - `hydrate_context()`
  - `persist_response_state()`
  - draft-based `looks_like_*` matchers
- [backend/trading-tool-backend/backend/infrastructure/repositories/conversation_state_repository.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/repositories/conversation_state_repository.py)

#### Expected QA impact

Very high.

This is one of the biggest drivers behind:

- multi-turn drift
- wrong toolflow activation
- wrong entity assumptions

#### Fix difficulty

Medium.

The logic is not huge, but it affects many flows and needs a proper state-isolation policy.

### 4. Setup / strategy context is sometimes wrong

#### Problem

FINN sometimes explains the wrong setup or routes based on the wrong active entity.

#### Most likely cause

The system has context, but it does not strongly model confidence in that context.

Today, context comes from multiple places:

- page payload
- symbol on page
- setup/bot/strategy ids from frontend
- conversation state
- inferred asset fallback
- saved database snapshots

When those disagree, the system does not yet have a strong “confidence policy” for:

- trusting the live page entity
- trusting a saved draft
- trusting the last persisted asset
- asking a clarifying question instead of assuming

#### Where it originates

- [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx)
  - frontend context payload construction
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)
  - direct forwarding of context into FINN hydration
- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
  - hydration and route selection
- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
  - resolved symbol priority engine

#### Expected QA impact

High.

This directly hurts:

- context awareness score
- product knowledge score
- user trust in entity-specific explanations

#### Fix difficulty

Medium to high.

The data is there; the hard part is designing safe precedence and ambiguity behavior.

### 5. Explain questions trigger create/update flows

#### Problem

Questions like:

- “Welke strategie bekijk ik nu?”
- “Leg mijn strategie uit”
- “Welke setup heb ik open?”

can trigger creation or update flows instead of explanation.

#### Most likely cause

Explain intent is not given strong enough priority over transactional intent.

The router has dedicated handlers for:

- status
- indicator insight
- coaching
- reports

but there is no equally strong “explain-first product entity” layer ahead of the create/update matchers.

That leaves room for:

- strategy words + context ids
- bot words + carried draft
- setup words + plan words

to be treated as transaction start/continuation instead of explanation.

#### Where it originates

- [backend/trading-tool-backend/backend/services/finn_plan_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/finn_plan_service.py)
  - ordering and strictness of `looks_like_*` request matchers
- [backend/trading-tool-backend/backend/api/ai_assistant_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/ai_assistant_api.py)
  - branch order for deterministic routes

#### Expected QA impact

High.

This hurts:

- general conversation quality
- product explanation quality
- tool safety perception

#### Fix difficulty

Low to medium.

Mostly a routing and contract problem, but it needs careful precedence rules.

### 6. Mission Control and specialized flows are strong, but the front door is uneven

#### Problem

Highly specialized flows often work well, while simple first-user questions fail or drift.

#### Most likely cause

FINN is currently optimized more as an operator engine than as a first-line assistant.

That means the strongest product quality today is in:

- mission control
- portfolio risk
- explain/review
- operator follow-through

But the weakest quality is in:

- general questions
- education
- broad product explanation
- ambiguous user phrasing

#### Where it originates

Systemic.

The current design puts more maturity into deterministic operator flows than into the generic assistant front door.

#### Expected QA impact

Very high.

This is the core reason why backend capability and user-facing QA quality can diverge so much.

#### Fix difficulty

Medium.

This requires a deliberate front-door product layer, not one isolated bugfix.

## Root Cause Matrix

| Problem | Likely cause | Origin file/service | QA impact | Fix difficulty |
| --- | --- | --- | --- | --- |
| Educational prompts fail | no dedicated education route; legacy fallback degrades to generic failure | `ai_assistant_service.py`, `ai_assistant_api.py` | Very high | Medium |
| Prompts fall into `bot_creation` / `strategy_creation` | transactional matchers too permissive | `finn_plan_service.py` | Very high | Low/Medium |
| Old drafts hijack new prompts | draft hydration and continuation policy too eager | `finn_plan_service.py`, `conversation_state_repository.py` | Very high | Medium |
| Wrong setup/strategy context | no context confidence / precedence model | frontend context + `finn_plan_service.py` + `ai_assistant_service.py` | High | Medium/High |
| Explain prompts trigger create/update | explain-first routing layer missing | `finn_plan_service.py`, `ai_assistant_api.py` | High | Low/Medium |
| General assistant feels weak despite strong product flows | operator engine stronger than front-door assistant layer | cross-cutting | Very high | Medium |

## Recommended Execution Order

The right order is not arbitrary. Each later fix depends on the earlier ones being clear enough.

### 1. Session State Isolation

Start here first.

Why first:

- stale state contaminates almost every other category
- if state remains sticky, router improvements still get hijacked
- it is one of the biggest sources of multi-turn drift

What to do next:

- define when a draft may continue
- define when it must be ignored
- add explicit reset and stale-draft invalidation rules

### 2. Router Hardening

Do this second.

Why second:

- once stale draft reuse is constrained, router logic becomes much more trustworthy
- this is where we separate:
  - general
  - coaching
  - explain
  - create/update
  - execute

### 3. Explain First

Do this third.

Why third:

- after state isolation and routing cleanup, entity questions can safely be defaulted into explain mode
- this directly improves first-user quality and product comprehension

### 4. Education Layer

Do this fourth.

Why fourth:

- education needs stable routing to be useful
- once explain/general lanes are reliable, education can be added as a safe high-confidence fallback

### 5. Context Confidence

Do this fifth.

Why fifth:

- context confidence is highly valuable, but it is more powerful once:
  - stale state is under control
  - routing is separated
  - explain mode is available
- otherwise the system will still misbehave even if context scoring exists

## Recommended Immediate Next Step

Use the new `FINN-P0-AUDIT` logs to collect a short live sample across these exact prompts:

1. general:
   - `Hoi FINN, wat kun je voor mij doen?`
2. education:
   - `Wat is RSI in simpele taal?`
   - `Wat is DCA?`
3. explain:
   - `Welke strategie bekijk ik nu?`
   - `Leg mijn setup uit`
4. coaching:
   - `Ik voel FOMO, wat moet ik doen?`
5. transactional:
   - `Maak een wekelijkse BTC setup voor een breakout long`

For each of those, compare:

- detected intent
- selected flow
- draft used yes/no
- selected entity
- success label

That dataset should then drive the actual P0 fixes instead of guessing from symptoms.

## Final Assessment

The main FINN P0 problem is not lack of capability.

The main problem is that the assistant front door is too porous:

- too easy for stale state to leak in
- too easy for transactional flows to claim questions they should not own
- too weak on education and simple explanation
- too willing to fall back into generic failure when it should produce a safe, grounded answer

That is why the right next move is:

1. instrument
2. confirm with live samples
3. then build the fixes in the recommended order above
