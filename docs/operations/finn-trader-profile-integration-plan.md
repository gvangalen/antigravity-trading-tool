# FINN Trader Profile Integration Plan

Last updated: 2026-06-21

## Purpose

The onboarding trader profile now exists, is stored, and can be edited later.

The next step is to make FINN actually use that profile consistently across:

- overlay briefing
- "Vandaag eerst"
- explain flows
- stateful chat/stream responses
- insight/explain actions
- report coaching surfaces

This plan covers the technical implementation required to move from:

- "profile captured"

to:

- "FINN is profile-aware"

## Scope

This plan covers:

1. normalized profile retrieval
2. backend context injection
3. prompt/context shaping
4. surface-level behavior changes
5. telemetry
6. rollout and verification

This plan does not yet cover:

- full coaching personality flags in production behavior
- profile-aware autonomous execution
- profile-driven filtering across every product page

## Desired outcome

After this plan:

- FINN knows what kind of trader the user is
- FINN explanation tone changes by profile
- FINN suppresses less relevant signal framing
- overlay briefing and "Vandaag eerst" feel aligned with user style
- profile usage is observable and testable

## Core principle

The trader profile must influence:

- relevance
- framing
- explanation depth
- warning intensity
- prioritization

It must not:

- silently override governance
- hard-lock users into one worldview
- cause hidden execution changes

## Canonical profile object

Create one canonical normalized object and use it everywhere in FINN.

Suggested shape:

```json
{
  "trader_types": ["investor", "swing_trader"],
  "primary_timeframes": ["4H", "1D"],
  "asset_focus": ["BTC", "CRYPTO"],
  "investment_goals": ["wealth_building"],
  "experience_levels": ["intermediate"],
  "risk_profiles": ["moderate"],
  "behavior_flags": [],
  "profile_completed_at": "2026-06-21T12:00:00Z",
  "profile_version": 1
}
```

Rules:

- arrays are always used, even when the user selected one value
- empty/missing values fall back to safe defaults
- FINN should receive both:
  - raw normalized values
  - a short human summary

## Recommended technical architecture

### 1. Central profile normalization service

Create or extend one backend helper/service that:

- reads assistant preferences / profile fields
- normalizes legacy scalar values into arrays
- returns the canonical profile object
- returns a short summary string for prompts

Suggested backend location:

- `backend/services/trader_profile_service.py`

Responsibilities:

- fetch user profile source data
- normalize profile shape
- fill safe defaults
- generate prompt-friendly summary text

Example summary:

```text
Trader profile:
- types: investor, swing trader
- active timeframes: 4H, 1D
- asset focus: BTC, crypto
- goal: wealth building
- experience: intermediate
- risk profile: moderate
```

### 2. FINN context injection layer

Inject the normalized profile into every major FINN path.

Minimum Phase 1 targets:

- `GET /api/assistant/finn/state`
- `GET /api/assistant/mission-control`
- `POST /api/assistant/insight`
- `POST /api/assistant/chat/stream`
- explain/decision actions triggered from overlay cards

The profile should be added to:

- context payloads
- routing metadata
- audit/event records where useful

### 3. Surface-specific shaping rules

Do not only pass the profile through.

Use it.

## Behavior rules by surface

### A. Overlay briefing

The briefing should use the profile in two ways:

1. market framing
2. action framing

Examples:

- investor / DCA:
  - "Voor jouw langere horizon verandert deze correctie je plan nu niet wezenlijk."
- swing trader:
  - "Voor jouw swing-profiel is dit nog geen sterke plek om nieuwe entries te forceren."
- day trader:
  - "Voor jouw kortere horizon is dit momentum zwak en wil je bevestiging zien."

Rules:

- use the user's chosen timeframe and style
- avoid irrelevant low-timeframe panic for long-horizon users
- use simpler wording for beginners
- use denser wording for advanced users

### B. "Vandaag eerst"

The top action should remain governance-driven, but the explanation should adapt.

Examples:

- conservative user:
  - stronger patience framing
- aggressive user:
  - same constraint, less parental tone
- beginner:
  - clearer explanation of what "review" means
- advanced:
  - more direct wording

### C. Explain / "Leg ... uit"

This is one of the highest-value integrations.

When the user asks FINN to explain a review, setup, or risk:

- tailor explanation depth to experience
- tailor relevance to trader type
- mention timeframe fit where relevant

Examples:

- beginner:
  - explain why the item matters in plain language
- swing trader:
  - focus on confirmation / setup quality
- investor:
  - focus on plan consistency and overreaction avoidance

### D. Stateful chat / stream responses

Profile should influence:

- tone
- examples
- what gets emphasized
- what gets deprioritized

Examples:

- investor:
  - less intraday noise
- swing trader:
  - 4H / Daily relevance
- scalper:
  - short-term invalidation / timing emphasis

### E. Report / coaching surfaces

Where FINN comments on user behavior:

- mention profile fit
- detect mismatch between action and stated style

Examples:

- "Dit wijkt af van je DCA-profiel."
- "Voor jouw swing-profiel lijkt dit te vroeg."
- "Voor jouw conservatieve profiel is deze setup nog te onrustig."

## Prompt shaping rules

Add a shared prompt fragment for profile-aware flows.

Suggested behavior contract:

```text
Use the trader profile to shape relevance and explanation tone.
Do not ignore governance or risk constraints.
Do not fabricate profile assumptions outside the provided profile.
If profile signals are mixed (for example investor + swing trader), prioritize the active page context and stated action.
```

Additional rules:

- if profile has multiple trader types:
  - prefer page/action context for the immediate answer
- if profile and current behavior conflict:
  - state the conflict clearly
- if profile is incomplete:
  - fall back gracefully without mentioning missing internals

## Prioritization logic

Profile should influence emphasis, not truth.

Order of authority:

1. governance / hard constraints
2. immediate entity context (bot/setup/decision/page)
3. trader profile
4. broader market framing

That keeps behavior safe and predictable.

## Recommended backend changes

### New service

- `backend/services/trader_profile_service.py`

Functions:

- `get_normalized_trader_profile(user_id, db)`
- `build_trader_profile_summary(profile)`
- `get_trader_profile_prompt_context(user_id, db)`

### Update likely callers

Likely touchpoints:

- `backend/api/ai_assistant_api.py`
- `backend/services/ai_assistant_service.py`
- `backend/services/finn_product_analytics_service.py` (telemetry only if needed)

### Add to response context

Where FINN builds envelopes or audit payloads, include:

- `trader_profile_used: true/false`
- `trader_profile_summary`
- `profile_match_mode`

Suggested values for `profile_match_mode`:

- `direct_match`
- `mixed_profile_page_context_priority`
- `profile_missing_fallback`

## Telemetry plan

Add events/fields that let us verify profile-aware behavior.

Track:

- `trader_profile_created`
- `trader_profile_updated`
- `finn_profile_context_used`
- `finn_profile_match_mode`
- `finn_profile_conflict_detected`

Useful metadata:

- trader types
- timeframes
- risk profile
- experience level
- flow type
- whether profile changed response framing

## Rollout plan

### Tranche 1: Data plumbing

- create central normalized profile service
- inject profile into FINN state/chat/insight contexts
- add telemetry fields

Success criteria:

- no user-facing changes required
- FINN logs show profile context being passed consistently

### Tranche 2: Overlay + explain behavior

- make briefing profile-aware
- make "Vandaag eerst" explanation profile-aware
- make explain/insight flows profile-aware

Success criteria:

- advice wording differs meaningfully by profile
- top action wording remains consistent with governance

### Tranche 3: Broader FINN behavior shaping

- stateful chat prompt shaping
- report coaching framing
- profile mismatch detection and coaching language

Success criteria:

- users experience FINN as a personal coach, not a generic explainer

### Tranche 4: Coaching personality extension

- behavior flags
- coaching-memory integration
- stronger habit-aware interventions

Success criteria:

- FINN can coach not just by market style but by user weakness patterns

## Test plan

### Functional profile fixtures

Test at least these profiles:

1. investor + weekly/monthly + conservative
2. DCA investor + BTC + beginner
3. swing trader + 4H/1D + moderate
4. day trader + 5m/15m + aggressive
5. hybrid investor + swing trader

### Expected behavior checks

Verify that:

- briefing wording changes by profile
- explain responses change by experience
- low-timeframe noise is reduced for investors
- day trader responses do not sound like long-term investing guidance
- conservative profiles get stronger patience framing
- mixed profiles do not create contradictory advice

### Regression guardrails

Verify that profile shaping does not:

- change hard governance decisions
- break context routing
- increase generic responses
- create prompt bloat that materially hurts latency

## Risks

### Risk: profile overpowers current context

Mitigation:

- page/entity context outranks profile when immediate action is specific

### Risk: prompt size grows too much

Mitigation:

- inject a compact normalized summary, not raw verbose data

### Risk: profile is stale after user edits it

Mitigation:

- always load current profile for stateful flows
- avoid long-lived stale client copies

### Risk: mixed multi-select profiles create mushy behavior

Mitigation:

- define match rules clearly
- prefer current page/entity context when profile contains multiple styles

## Acceptance criteria

This work is done when:

- FINN receives normalized trader profile context in all target flows
- overlay briefing changes meaningfully by profile
- explain flows adapt tone/relevance by profile
- telemetry confirms profile-aware behavior is being used
- advice feels more personally relevant without becoming inconsistent

## Recommendation

Treat this as the next direct follow-up to trader-profile onboarding.

The onboarding profile has value only if FINN actually changes because of it.

That means the next product milestone is:

- not more profile collection
- but profile-aware FINN behavior

