# Product Polish Audit

Last updated: 2026-06-24

## Scope

This audit combines:

- live visual review of the current public product
- user-provided live screenshots of authenticated product surfaces
- direct string and source scan in the frontend codebase

Audited surfaces:

- landing page
- login
- register
- onboarding overview
- profile / trader profile
- reports / Finn report framing
- global nav / avatar menu
- notification toggle
- visible production console noise

## Overall read

The product is no longer in a "prototype only" state.
The core shape is credible, the design language is recognizably premium, and several key surfaces now feel much stronger than before.

The biggest remaining launch risk is not missing functionality.
It is polish inconsistency:

- mixed Dutch / English in the same journeys
- hardcoded copy bypassing translations
- visible production debug noise
- a few placeholder or operator-flavored labels still leaking into user-facing UI

## Recommended readiness label

- current polish readiness: `caution`
- recommended next move: one dedicated product-polish sprint before any major new feature wave

## Priority backlog

### P1

#### 1. Product language strategy is inconsistent across the same user journey

Why it matters:

- this is the biggest visible trust leak in the current product
- the app feels half-translated instead of intentionally bilingual

Evidence:

- landing page is fully English:
  - [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:75)
  - [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:182)
- login page is largely Dutch:
  - [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:90)
- authenticated profile and report surfaces mix both:
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:230)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1186)

Fix direction:

- decide primary language per product surface
- remove ad hoc language mixing
- only keep bilingual behavior behind explicit locale switching

#### 2. Trader profile page still ships user-facing hardcoded English copy outside the translation system

Why it matters:

- this page is now strategically important and highly visible
- it is exactly the wrong place for mixed-language leakage

Evidence:

- hardcoded account labels:
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:230)
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:240)
- hardcoded profile summary card:
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:250)
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:253)
- hardcoded subscription copy:
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:270)
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:283)
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:288)

Fix direction:

- move all visible copy on this page into dictionaries
- use locale-aware copy for account card, subscription card, helper card, and CTA

#### 3. Finn report framing still mixes Dutch product copy with English audit labels

Why it matters:

- reports are one of the most product-defining surfaces
- the current copy feels partially internal instead of fully productized

Evidence:

- Dutch body copy with English labels:
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1183)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1192)
- awkward hybrid phrasing:
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1186)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1229)

Fix direction:

- rewrite the Finn report framing as one coherent product language block
- rename audit-style tags into human product copy

#### 4. Onboarding overview is wired to translation keys that do not exist

Why it matters:

- this creates missing labels, blank UI text, or accidental fallback behavior
- onboarding is the first structured guided experience in the product

Evidence:

- code references keys such as:
  - `onboardingOverview.nextStep`
  - `onboardingOverview.finnLabel`
  - `chips.noLiveTrades`
  - `chips.finnHelps`
  - [frontend/trading-tool-frontend/app/onboarding/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/onboarding/page.jsx:185)
  - [frontend/trading-tool-frontend/app/onboarding/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/onboarding/page.jsx:197)
  - [frontend/trading-tool-frontend/app/onboarding/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/onboarding/page.jsx:214)
  - [frontend/trading-tool-frontend/app/onboarding/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/onboarding/page.jsx:218)
- dictionaries currently define different names:
  - [frontend/trading-tool-frontend/dictionaries/en.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/en.json:276)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:276)

Fix direction:

- align code and dictionary keys exactly
- remove silent null rendering from onboarding hero chips and helper text

#### 5. Public landing page still contains placeholder legal links

Why it matters:

- dead `Terms`, `Privacy`, and `Security` links on the marketing page are not launch-grade
- this is a trust and compliance smell on a live public surface

Evidence:

- [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:279)
- [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:280)
- [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:281)

Fix direction:

- either provide real pages
- or remove these links until legal pages exist

#### 6. Production console output is too noisy for a polished live experience

Why it matters:

- it makes debugging harder
- it reduces confidence during QA, demos, and production support
- some user screenshots already show this noise constantly

Evidence:

- onboarding debug logs are still shipped:
  - [frontend/trading-tool-frontend/hooks/useOnboarding.js](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/hooks/useOnboarding.js:34)
  - [frontend/trading-tool-frontend/hooks/useOnboarding.js](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/hooks/useOnboarding.js:40)
  - [frontend/trading-tool-frontend/hooks/useOnboarding.js](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/hooks/useOnboarding.js:146)
  - [frontend/trading-tool-frontend/hooks/useOnboarding.js](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/hooks/useOnboarding.js:189)
- market debug log still shipped:
  - [frontend/trading-tool-frontend/components/bot/MarketDecisionCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/MarketDecisionCard.jsx:79)
- notification timeout warning leaks into normal usage:
  - [frontend/trading-tool-frontend/components/NotificationToggle.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/NotificationToggle.jsx:22)

Fix direction:

- remove nonessential console logging from production code paths
- downgrade recoverable warning flows into silent or stateful UX handling

### P2

#### 7. Dutch dictionary still contains many English product terms, weakening the locale experience

Why it matters:

- even with locale switching, the Dutch experience does not feel deliberately translated

Evidence:

- navigation and system terms:
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:31)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:35)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:36)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:39)
- dashboard terms still mixed:
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:52)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:55)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:83)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:99)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:102)
- trader profile terms still mixed:
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:119)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:129)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:223)

Fix direction:

- do a dictionary-first normalization pass
- decide which product nouns intentionally stay English and codify them

#### 8. Avatar/profile menu is better than before, but still not fully polished linguistically

Why it matters:

- the account menu is a high-frequency surface
- small wording issues stand out there quickly

Evidence:

- `Level:` remains English in Dutch locale:
  - [frontend/trading-tool-frontend/components/ui/AvatarMenu.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AvatarMenu.jsx:137)
- `Profiel & trader-profiel` is workable but clunky:
  - [frontend/trading-tool-frontend/components/ui/AvatarMenu.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AvatarMenu.jsx:144)

Fix direction:

- rewrite this menu for clarity and brevity
- ensure all labels are product-consistent with the profile page naming

#### 9. Login and register feel visually premium, but their copy tone does not match the rest of the product strategy yet

Why it matters:

- authentication is the entry funnel into the product
- the current voice is neither fully Dutch-product nor fully English-brand

Evidence:

- Dutch login copy:
  - [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:90)
- English landing copy:
  - [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:75)

Fix direction:

- align the landing/auth tone into one intentional acquisition journey

#### 10. Notification UX is functionally better than before, but not yet product-grade

Why it matters:

- this is a small but user-facing system feature
- current fallback behavior still smells technical rather than polished

Evidence:

- timeout-driven warning:
  - [frontend/trading-tool-frontend/components/NotificationToggle.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/NotificationToggle.jsx:17)
- mixed UX strings:
  - [frontend/trading-tool-frontend/components/NotificationToggle.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/NotificationToggle.jsx:69)
  - [frontend/trading-tool-frontend/components/NotificationToggle.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/NotificationToggle.jsx:83)

Fix direction:

- localize all error states
- avoid technical-sounding fallback copy in user-visible flows

### P3

#### 11. Some premium-style copy is still more "cool" than concrete

Why it matters:

- this is not broken, but it can feel slightly over-styled for product clarity

Evidence:

- landing and pricing voice:
  - [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:73)
  - [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:183)
- login CTA wording:
  - [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:158)

Fix direction:

- keep the premium identity
- trim copy that sounds more theatrical than useful

#### 12. Naming consistency is still loose across plan labels and product nouns

Why it matters:

- these are small inconsistencies, but they accumulate

Evidence:

- `Basis Plan` / `Basic` / `Pro Level` style mixing:
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:272)
  - [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:288)
  - [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:192)

Fix direction:

- define one naming table for plans, reports, profile labels, and product nouns

## Suggested fix order

### Wave 1

- fix missing onboarding translation keys
- remove production debug logs
- remove mixed-language hardcoded copy from profile page
- fix report header/badge language
- replace dead landing-page legal links

### Wave 2

- normalize dictionaries
- align landing/login/register tone
- clean notification strings and states
- tighten avatar menu wording

### Wave 3

- do a final copy/tone pass across all core surfaces
- run live regression on onboarding, profile, report, dashboard, and assistant

## Definition of done for this audit

This audit is considered resolved when:

- all P1 issues are fixed
- no core live journey visibly mixes English and Dutch by accident
- no major product page leaks debug logging or technical placeholder behavior
- public-facing legal/footer links are real or intentionally removed
- QA can describe the product as coherent, not just functional
