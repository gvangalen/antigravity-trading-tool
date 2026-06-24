# Product Go-Live Polish Plan

Last updated: 2026-06-24

## Purpose

This plan defines the highest-leverage path from "feature-rich and promising" to "ship-ready and trustworthy".

The goal is not to add more product surface first.
The goal is to make the current product feel:

- consistent
- fast enough
- understandable
- professional
- safe to expose to real users on live

## Recommendation

The next major step should be:

1. product polish
2. release hardening
3. end-to-end QA and acceptance
4. only then the next major feature wave

Reason:

- the core FINN profile and behavioral system is now strong enough that polish and reliability have more leverage than adding net-new capability
- mixed language, AI placeholder copy, uneven UX, and edge-case instability hurt launch quality more than a missing extra feature
- a disciplined polish pass also makes later feature work cleaner and faster

## Go-live outcome

We should consider the current product "ready for a real live push" when all of the following are true:

- all core user-facing flows are understandable without internal context
- Dutch and English usage is intentional and consistent per surface
- placeholder / generic AI copy is removed from visible user paths
- loading, empty, and error states feel deliberate instead of broken
- core flows are fast and stable enough on real production infra
- operator health, logs, telemetry, and rollback paths are usable
- QA can score the release as product-credible, not just technically green

## Workstreams

### 1. Copy and language consistency

Goal:

- remove mixed-language friction
- remove obviously AI-sounding or placeholder copy
- make tone consistent across onboarding, dashboard, reports, profile, bot, and admin

Scope:

- headers
- button labels
- section descriptions
- onboarding questions
- toasts / snackbars
- validation messages
- empty states
- loading states
- error states
- report labels
- profile labels

Checklist:

- [ ] define product language rule per surface:
  - public/product UX primarily Dutch or primarily English
  - admin/operator surfaces may be separate if intentional
- [ ] remove mixed NL/EN labels in the same user flow
- [ ] replace placeholder or generic AI copy
- [ ] normalize terminology:
  - `Finn`
  - `report`
  - `profile`
  - `setup`
  - `coach/coaching`
  - `risk`
- [ ] rewrite weak system messages into product-grade copy
- [ ] ensure all empty states explain what to do next
- [ ] ensure all destructive or risky actions use clear language

Exit criteria:

- no obvious mixed-language moments in core user flows
- no "AI draft" feeling on top-level product surfaces
- one consistent tone of voice across the main app

### 2. UX and visual product polish

Goal:

- make the app feel intentional and production-ready
- remove duplicate CTAs, confusing hierarchy, and awkward spacing

Scope:

- overview/dashboard
- reports
- profile
- onboarding
- assistant/bot
- report detail and tabs
- mobile navigation and touch behavior

Checklist:

- [ ] remove duplicate actions and duplicate explanations
- [ ] tighten visual hierarchy on major pages
- [ ] check spacing and card balance on desktop
- [ ] check spacing and stacking on mobile
- [ ] improve clarity of active / inactive / loading states
- [ ] verify forms are easy to scan and submit
- [ ] ensure tabs, filters, and selectors are understandable
- [ ] ensure empty states are helpful instead of sparse
- [ ] ensure primary CTA is always obvious

Exit criteria:

- no major page feels cluttered, duplicated, or unfinished
- no core flow depends on the user "guessing" what to do next

### 3. Frontend reliability and edge-case cleanup

Goal:

- make visible product behavior robust in real usage

Scope:

- auth/session behavior
- cached state
- retry paths
- stale loading states
- client-side errors
- SSR/static export quirks
- mobile/browser compatibility

Checklist:

- [ ] verify login, refresh, logout, and expired-session behavior
- [ ] verify onboarding completion and redirect behavior
- [ ] verify profile save/load/edit roundtrips
- [ ] verify report loading under slow or partial backend responses
- [ ] verify assistant/chat requests do not fail from CSRF/session mismatch
- [ ] verify stale data does not survive account changes
- [ ] remove noisy console errors and warnings on main flows
- [ ] check Safari behavior on main product surfaces
- [ ] check mobile browser behavior on main product surfaces

Exit criteria:

- no known recurring frontend errors on core flows
- no core page gets stuck in broken loading/retry states

### 4. Backend and operational hardening

Goal:

- make production behavior reliable enough that QA and live usage mean something

Scope:

- API stability
- migrations
- background jobs
- queue health
- telemetry
- deploy safety
- rollback confidence

Checklist:

- [ ] confirm all required tables/migrations exist on live
- [ ] confirm FAISS/vector search path loads cleanly where expected
- [ ] confirm assistant/report/profile endpoints behave correctly under auth
- [ ] confirm Celery workers and queue routing are healthy
- [ ] confirm retries are controlled and not hiding failures
- [ ] confirm health endpoints reflect reality well enough for operators
- [ ] confirm deploy and rollback steps are current
- [ ] confirm production logging is sufficient for debugging user issues

Exit criteria:

- no known missing infra dependency for core product paths
- production deploys are repeatable and reversible

### 5. Performance and perceived speed

Goal:

- reduce the feeling that the app is heavy or slow

Scope:

- dashboard load
- reports load
- market data fetch behavior
- assistant/report API roundtrip cost
- frontend overfetching

Checklist:

- [ ] measure slowest high-traffic pages on live
- [ ] reduce unnecessary duplicate requests
- [ ] identify blocking API chains on dashboard/report/profile
- [ ] improve skeleton/loading behavior where wait time is unavoidable
- [ ] cache or prefetch where it materially improves perceived speed
- [ ] verify production build output is clean and current

Exit criteria:

- major pages feel responsive enough for normal daily use
- user frustration is not driven by obvious wait loops or overfetching

### 6. Core flow certification

Goal:

- validate that the actual product journey is ready, not just isolated endpoints

Must-pass flows:

- [ ] register/login
- [ ] onboarding
- [ ] onboarding trader profile
- [ ] dashboard landing
- [ ] report open and refresh
- [ ] Finn report behavior
- [ ] assistant/general help
- [ ] profile view and edit
- [ ] logout and relogin persistence

Quality checks per flow:

- [ ] understandable first impression
- [ ] no broken or embarrassing copy
- [ ] no dead-end state
- [ ] no console-breaking error
- [ ] acceptable speed
- [ ] acceptable mobile behavior

Exit criteria:

- every core flow can be demoed cleanly end-to-end on live

### 7. Release gate

Goal:

- define when we stop polishing and actually ship with confidence

Release criteria:

- [ ] product polish pass completed
- [ ] live critical bugs list empty
- [ ] no open blocker in auth, onboarding, profile, reports, or assistant
- [ ] QA pass on live-like environment completed
- [ ] product owner signoff on visible copy and UX
- [ ] rollback path verified
- [ ] post-launch monitoring plan ready

Recommended launch bar:

- zero known P0 issues
- zero known P1 issues in core flows
- only minor P2/P3 cosmetic follow-ups allowed

## Suggested execution order

### Phase 1: copy and UX pass

Do first:

1. language consistency sweep
2. remove AI/placeholder copy
3. remove duplicate CTAs and awkward layout moments
4. tighten empty/loading/error states

Expected output:

- one tracked punch list of product polish issues
- one visible improvement pass across the major pages

### Phase 2: core flow cleanup

Do next:

1. onboarding
2. reports
3. profile
4. assistant/bot
5. dashboard

Expected output:

- core product journey feels coherent and dependable

### Phase 3: performance and hardening

Do next:

1. inspect slow pages and duplicate fetches
2. clean production warnings/errors
3. verify operational dependencies and telemetry
4. verify deploy/rollback confidence

Expected output:

- fewer incidents
- better perceived speed
- better operator confidence

### Phase 4: final QA and signoff

Do last:

1. run full regression on core flows
2. run role-based and device-based spot checks
3. score release readiness
4. decide go / no-go

Expected output:

- final launch verdict with explicit blockers or signoff

## Practical first punch list

If we start immediately, these are the best first tasks:

1. Do a full NL/EN and placeholder-copy sweep on:
   - onboarding
   - profile
   - reports
   - dashboard
   - bot/assistant
2. Build one product-polish backlog with screenshots and severity:
   - `P0` broken flow
   - `P1` major UX/copy issue in core flow
   - `P2` noticeable but not launch-blocking
   - `P3` cosmetic
3. Clean the top 10 visible UX/copy issues first.
4. Then run a dedicated live-readiness QA pass.

## What not to do yet

Avoid this until the polish pass is complete:

- large new feature branches
- redesigning stable surfaces from scratch
- expanding into adjacent modules before the core is clean
- accepting mixed language or placeholder copy as "good enough for now"

## Recommended next Codex task

The strongest immediate next task is:

- run a full product-polish audit across the live app and turn it into a prioritized fix list with screenshots, file targets, and severity

That gives us the cleanest path to a real launch push.
