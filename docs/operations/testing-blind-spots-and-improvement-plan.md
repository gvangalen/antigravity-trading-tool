# Tradamind Testing Blind Spots And Improvement Plan

Last updated: 2026-06-10

## Purpose

This note captures the main reasons why recent testing missed a few important live issues, and what we should change so the next rounds catch them earlier.

This is not a blame document.
It is a calibration document.

The goal is simple:

- catch more live-feeling issues before users feel them
- reduce the gap between "tests passed" and "product feels right"
- make design, QA, systems, and operator testing reinforce each other

## What We Learned

Recent misses were real and instructive:

1. the live app felt slow even while basic health checks were green
2. Finn report placement felt off on the Report page even after design review
3. AI budget burn was not clearly attributable in admin views
4. background jobs and QA activity could affect production feel and spend without being obvious in the main product telemetry

These are not random misses.
They point to repeatable blind spots in how we test.

## Main Blind Spots

### 1. Too much focus on "works" and not enough on "feels right"

Many checks currently validate:

- route returns `200`
- API responds
- page renders
- prompt routes correctly
- deploy finishes

Those are necessary.
They are not sufficient.

They do not reliably catch:

- slow or heavy-feeling screens
- awkward content hierarchy
- layout that is technically valid but visually wrong
- "this reads strangely in context" issues

### 2. Staging is useful, but live is still different

Staging and live are intentionally separated:

- separate database
- separate Redis
- separate env
- separate users

That is correct operationally.
But it means staging does not automatically reveal:

- live backlog buildup
- live report history quality
- live auth/session edge cases
- real production budget pressure
- real user traffic patterns

### 3. Synthetic checks miss long-tail UX and ops drift

Many automated checks hit a narrow happy path:

- one or two prompts
- one route
- one user
- one moment in time

They do not naturally catch:

- queue buildup over hours or days
- stale browser session behavior
- old cookies/CSRF interactions
- layout oddities after multiple UI changes
- background jobs quietly consuming AI budget

### 4. Product telemetry and AI spend telemetry were split

We already had good progress on:

- screen views
- onboarding funnel
- prompt usage
- confirm funnel

But we did not yet have equally clear separation for:

- live user AI spend
- QA/staging AI spend
- background job AI spend
- blocked/quota-hit AI attempts

That created a gap between:

- "what users did"
- "what cost money"

### 5. Agents test from their role, not from full product reality

This is expected.

A design agent naturally emphasizes:

- visual hierarchy
- consistency
- trust feel

A systems agent naturally emphasizes:

- health
- workers
- queues
- deployment/runtime behavior

A QA agent naturally emphasizes:

- correctness
- known scenarios
- regression coverage

What can still slip through is exactly the overlap:

- a design issue that only appears in live context
- an ops problem that still returns `200`
- a product-quality issue that is not a hard failure

## Improvement Plan

## P0 — Add a live reality pass after staging signoff

Every meaningful tranche should end with a short live pass, not only staging confirmation.

Required live checks:

- one existing real user session
- one fresh session when relevant
- one report route
- one core Finn flow
- one admin/ops route if the change affects observability

Success condition:

- live feels consistent with staging intent
- no major "works but feels wrong" mismatch remains

## P0 — Split testing into four lenses explicitly

For important releases, test with these four lenses on purpose:

1. functional correctness
2. UX/readability/hierarchy
3. operational/runtime behavior
4. cost and telemetry behavior

Do not let one agent implicitly stand in for all four.

### Practical rule

Every release note or QA handoff should say which of these four lenses were actually covered.

## P0 — Keep user telemetry and AI spend telemetry side by side

We now have better foundations for this.
The next discipline is to use both views together.

For AI-heavy features, always inspect:

- what users clicked
- what prompts they sent
- what AI source generated cost
- what background jobs ran
- what blocked on quota

Success condition:

- we can answer "who used it?" and "what spent money?" from the same review cycle

## P1 — Add explicit slow-feel checks, not only response checks

For the main live surfaces:

- dashboard
- report
- setup
- admin telemetry

check not only status and payload, but:

- page visibly settles
- key blocks appear in the expected order
- loading is not stuck too long
- critical calls are not timing out or queuing badly

This can be lightweight.
It just needs to be deliberate.

## P1 — Add "new user" and "existing user" test paths

We should test both:

- fresh onboarding user
- returning real user with existing data

Why:

- onboarding catches first-session friction
- existing users catch report history, stale state, AI history, and real-world clutter

Some issues only exist in one of those two worlds.

## P1 — Add background automation checks to release review

When a release touches AI, reports, Celery, or observability, add a release check for:

- daily report job
- weekly/monthly/quarterly jobs if relevant
- queue depth after rollout
- recent AI usage logs for background jobs

Success condition:

- background automation is treated as a first-class production actor, not invisible machinery

## P2 — Maintain a known blind-spots checklist

For the next sprints, keep an explicit checklist for:

- live vs staging mismatch
- browser cache / CSRF / old session behavior
- layout hierarchy regressions
- queue creep
- hidden background cost
- quota-blocked AI paths

This should be small and reusable, not a huge process artifact.

## Proposed Release Checklist Additions

Add these items to future signoff:

- `Live existing-user pass completed`
- `Live new-user pass completed` when onboarding is affected
- `Background job cost/source visible`
- `Admin telemetry checked`
- `Queue depths checked after rollout`
- `One design hierarchy pass on live route`

## Recommended Ownership

### Design review

Should explicitly answer:

- is the hierarchy right on the real page?
- does this feel calm and intentional in context?

### QA review

Should explicitly answer:

- do the main flows behave correctly?
- are fallback/error/edge paths still sensible?

### Systems review

Should explicitly answer:

- does the runtime stay healthy under actual production conditions?
- are queues, workers, and deploy state stable?

### Operator/product review

Should explicitly answer:

- does this create or hide cost?
- can we see usage and spend clearly afterward?

## Exit Condition

We should consider this plan adopted when:

- future release handoffs explicitly mention the four testing lenses
- live passes are no longer optional after staging signoff
- cost/source visibility is reviewed alongside user telemetry
- major "how did testing miss this?" moments become rarer and narrower

## Short Version

The core lesson is:

- passing tests is not the same as a good live experience

So the fix is not "test more randomly."
The fix is:

- test across the right lenses
- include live reality earlier
- treat background jobs and spend as first-class behavior
- and deliberately review both correctness and feel
