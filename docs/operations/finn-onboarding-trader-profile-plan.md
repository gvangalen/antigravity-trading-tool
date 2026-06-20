# FINN Onboarding Trader Profile Plan

Last updated: 2026-06-17

## Purpose

This plan adds a structured trader profile to onboarding so FINN can adapt:

- advice quality
- risk framing
- setup relevance
- timeframe relevance
- coaching tone

The goal is simple:

FINN should stop acting like a generic market explainer and start acting like a coach for the specific kind of trader using Tradamind.

## Why this matters

The current product knows a lot about:

- macro
- technical
- setups
- strategies
- bots

But it still knows too little about the user.

That creates a real quality ceiling.

The same market state should not lead to the same advice for:

- a long-term DCA investor
- a weekly swing trader
- a 15m day trader

Without a user profile, FINN can only partially personalize.

With a trader profile, FINN can:

- suppress irrelevant signals
- prioritize the right setups
- frame warnings in a way that matches the user's horizon
- explain things at the right experience level
- coach around the user's likely weaknesses

## Product outcome

After this plan:

- onboarding collects a usable trader profile
- the profile is stored durably
- FINN reads the profile in its routing and response generation
- trader-facing surfaces can adapt to the profile
- future coaching and personalization work has a clean foundation

## Scope

This plan covers:

1. onboarding questions
2. backend profile storage
3. frontend onboarding implementation
4. FINN prompt/context integration
5. future coaching extensions

This plan does not yet include:

- full profile editing UX
- full per-strategy personalization engine
- automatic migration of old users into fully completed profiles

## Proposed profile model

Store a trader profile as a user-owned structured object.

Suggested logical shape:

```json
{
  "trader_type": "swing_trader",
  "primary_timeframes": ["4H", "1D"],
  "asset_focus": ["BTC", "CRYPTO"],
  "goal": "wealth_building",
  "experience_level": "intermediate",
  "risk_profile": "moderate",
  "behavior_flags": [],
  "profile_completed_at": "2026-06-17T10:00:00Z",
  "profile_version": 1
}
```

## Phase 1: Core trader profile

Phase 1 should be small enough to ship safely, but useful enough that FINN becomes immediately smarter.

### Step 1: Trader type

Single choice:

- Investor
- DCA Investor
- Swing Trader
- Day Trader
- Scalper
- Hybrid

Why:

- determines holding horizon
- determines signal sensitivity
- helps FINN avoid giving intraday advice to long-horizon users

### Step 2: Primary timeframes

Multi-select:

- 5m
- 15m
- 1H
- 4H
- Daily
- Weekly
- Monthly

Why:

- determines what chart context matters
- helps suppress noisy low-timeframe suggestions for longer-term users

### Step 3: Asset focus

Multi-select:

- Bitcoin
- Crypto broad market
- Stocks
- ETFs
- Forex
- Commodities

Why:

- helps FINN prioritize relevant examples and warnings
- helps future filtering of setups and reports

### Step 4: Goal

Single choice:

- Build wealth
- Generate extra income
- Trade actively
- Preserve capital
- Financial independence
- Retirement

Why:

- same signal should be framed differently for capital preservation vs active trading

### Step 5: Experience level

Single choice:

- Beginner
- Intermediate
- Advanced
- Professional

Why:

- changes explanation depth
- affects how much jargon FINN can safely use

### Step 6: Risk profile

Single choice:

- Conservative
- Moderate
- Aggressive

Why:

- changes warning style
- changes how FINN frames patience, confirmation, and drawdown tolerance

## Phase 2: Coaching personality extension

This should not block Phase 1.

After the base profile works, add behavior/coaching traits:

- I take profit too early
- I hold losers too long
- I overtrade
- I get FOMO
- I miss entries
- I use too much leverage

Suggested storage:

```json
{
  "behavior_flags": [
    "takes_profit_too_early",
    "holds_losers_too_long",
    "fomo"
  ]
}
```

Why this matters:

- this is where FINN becomes a real trading coach
- these flags can sharpen review copy, warnings, and habit feedback

## UX design principles

The trader profile should feel:

- short
- confidence-building
- useful

It should not feel like:

- a compliance form
- a survey
- a heavy settings panel

### Recommended onboarding behavior

- keep each step visually simple
- explain why the question matters
- allow skipping only where reasonable
- summarize the profile before finishing

### Recommended copy style

Use plain user language such as:

- "What kind of trader are you?"
- "Which chart timeframes do you actually use?"
- "What are you mainly trying to achieve?"

Avoid system-like copy such as:

- "Select your operating class"
- "Choose execution horizon"

## Suggested onboarding flow

Recommended order:

1. trader type
2. timeframes
3. asset focus
4. goal
5. experience
6. risk profile
7. profile summary

Optional final summary:

```text
You trade mostly as a swing trader on 4H and Daily.
You focus on BTC and crypto.
Your profile is moderate-risk and growth-oriented.

FINN will now tailor explanations, warnings, and next steps to this style.
```

## Backend implementation

## Data storage options

Preferred option:

- add explicit trader profile fields to the user profile domain

Good fallback option:

- store as structured JSON on a profile/preferences model

Recommendation:

Use explicit structured fields if they are likely to affect many product surfaces.

Suggested fields:

- `trader_type`
- `primary_timeframes`
- `asset_focus`
- `goal`
- `experience_level`
- `risk_profile`
- `behavior_flags`
- `profile_completed_at`
- `profile_version`

## API changes

Add or extend endpoints to support:

- fetch current trader profile
- save/update trader profile
- mark profile completion state

Suggested usage:

- onboarding writes the profile
- settings/profile page can later edit it
- FINN state endpoints can include a normalized profile summary

## Frontend implementation

## Onboarding screens

Current onboarding should gain a new profile section or a dedicated profile step sequence.

Recommended implementation:

- keep current onboarding steps intact
- insert a dedicated "Trading profile" block after the user understands the product
- do not mix product education and profile questions inside the same card

Suggested components:

- `TraderTypeStep`
- `TimeframeStep`
- `AssetFocusStep`
- `GoalStep`
- `ExperienceStep`
- `RiskProfileStep`
- `TraderProfileSummaryStep`

## Progressive save behavior

Save per step, not only at the end.

Why:

- better resilience
- easier telemetry
- less loss if the session is interrupted

## Telemetry to add

Track:

- `trader_profile_step_started`
- `trader_profile_step_completed`
- `trader_profile_completed`
- selected values per step in metadata

This matters because we want to know:

- where users hesitate
- which profiles are most common
- whether certain profile types convert differently

## How FINN should use the profile

This is the most important part.

Do not collect profile data unless FINN actually uses it.

## Immediate integrations

Phase 1 should change FINN in these ways:

### 1. Prompt/context shaping

Include the normalized trader profile in FINN context payloads.

FINN should know:

- trader type
- preferred timeframes
- asset focus
- experience
- risk profile
- primary goal

### 2. Advice filtering

Examples:

- avoid intraday trade suggestions for investors
- avoid weekly-only abstractions for active day traders
- reduce irrelevant setup suggestions outside chosen timeframes

### 3. Explanation style

Examples:

- beginner -> simpler explanations, more caution
- advanced -> shorter, denser explanations

### 4. Risk framing

Examples:

- conservative profile -> stronger patience language
- aggressive profile -> still governed, but less overprotective framing

### 5. Review and coaching tone

Examples:

- DCA user:
  - "This RSI spike does not break your longer-term accumulation plan."
- swing trader:
  - "This entry is still early; wait for confirmation on your active timeframe."

## Routing implications

Over time, the profile should influence:

- what FINN surfaces first
- what "Vandaag eerst" prioritizes
- which warnings are emphasized
- which signals are muted

It should not bypass governance.

The profile shapes explanation and prioritization, not autonomous execution.

## Acceptance criteria

This feature is successful when:

### Product

- onboarding collects a complete trader profile without feeling heavy
- users understand why FINN asks these questions
- the resulting profile summary feels accurate and useful

### Technical

- profile data is stored durably
- profile can be fetched reliably after onboarding
- FINN receives a normalized trader profile in context

### FINN behavior

- advice clearly changes by trader type and timeframe
- explanations change by experience level
- warnings change by risk profile
- irrelevant signals are reduced

## Rollout plan

### Tranche A

- data model
- backend API
- frontend onboarding profile steps
- telemetry

### Tranche B

- FINN context integration
- prompt shaping
- explanation personalization

### Tranche C

- coaching personality extension
- profile editing in settings
- profile-aware filtering in more product surfaces

## Risks and guardrails

### Risk: too much onboarding friction

Mitigation:

- keep the questions short
- use clear defaults
- avoid long explanations

### Risk: profile collected but not actually used

Mitigation:

- do not ship Phase 1 without at least basic FINN context integration

### Risk: overfitting the advice

Mitigation:

- the profile should guide relevance and framing
- it should not hard-lock the user out of other valid perspectives

## Recommendation

This should be treated as the next high-value product step for FINN.

It is not just an onboarding improvement.

It is the foundation for:

- real personalization
- better advice quality
- stronger coaching
- better signal relevance

In short:

this is one of the clearest paths from "smart assistant" to "personal trading coach."
