# Product-Wide UI Copy Audit

Last updated: 2026-06-24

## Scope

This sweep covered the full frontend source tree for the main Tradamind product:

- all `app/**/page.jsx` surfaces
- shared UI components
- cards
- tables
- report components
- bot components
- admin pages
- Finn assistant overlay
- Dutch dictionary consistency

This was a source-level product audit, not a browser-click regression of every path.
It is strong enough to identify the remaining launch-quality gaps, especially mixed language, AI placeholder copy, operator language, and unfinished table/card framing.

## Overall Read

The core user profile and FINN work is now in much better shape than before.
But the product as a whole is not yet uniformly polished.

The remaining problems are concentrated in:

- shared terminal/HUD components
- strategy and bot product flows
- admin/operator pages
- report generation states
- the large FINN assistant overlay

The biggest risk is no longer one broken flow.
It is inconsistency across surfaces:

- polished pages next to obviously internal/operator pages
- Dutch user-facing flows next to English or hybrid cards
- some real product text next to placeholder/mock/diagnostic copy

## Coverage

Reviewed source surfaces include:

- [frontend/trading-tool-frontend/app/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/page.jsx:1)
- [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:1)
- [frontend/trading-tool-frontend/app/(public)/register/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/register/page.jsx:1)
- [frontend/trading-tool-frontend/app/onboarding/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/onboarding/page.jsx:1)
- [frontend/trading-tool-frontend/app/onboarding/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/onboarding/profile/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/dashboard/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/dashboard/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/market/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/market/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/macro/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/macro/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/technical/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/technical/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/setup/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/setup/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/bot/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/bot/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx:1)
- [frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx:1)
- [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:1)
- [frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx:1)
- [frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx:1)
- [frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx:1)

## Priority Findings

### P1

#### 1. The product still ships obvious placeholder and mock content on user-facing surfaces

Why it matters:

- this is the clearest remaining “not fully finished” signal
- it breaks trust faster than mixed tone alone

Evidence:

- hardcoded mock advice:
  - [frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx:14)
  - [frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx:25)
- explicit placeholder reason:
  - [frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/dashboard/TradingAdvice.jsx:27)

Fix direction:

- remove the mock advice card entirely until live-backed
- or rewire it to real data with polished empty/loading/error states

#### 2. Strategy flow is still heavily English while the surrounding protected product is increasingly Dutch

Why it matters:

- this is a high-visibility core workflow
- users will feel the jump immediately between profile/report and strategy

Evidence:

- page header and summary labels:
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:102)
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:116)
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:143)
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:178)
- toast states remain English:
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:60)
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:68)
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:78)
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:89)

Fix direction:

- fully localize strategy page headers, CTA labels, placeholders, drawer labels, and snackbars
- align it with the same product language rule used in profile/report

#### 3. Report generation and PDF states still leak English operational copy

Why it matters:

- reports are a flagship product surface
- generation, retry, and PDF handling are exactly where product polish should stay strong

Evidence:

- generation messaging:
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1567)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1574)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1577)
- PDF/download messaging:
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1590)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1603)
  - [frontend/trading-tool-frontend/app/(protected)/report/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/report/page.jsx:1607)

Fix direction:

- rewrite all report generation, retry, and PDF messages into one coherent user-facing Dutch block
- keep operator/debug wording out of the user path

#### 4. Shared macro/report HUD components still read like internal premium mockups rather than final product UI

Why it matters:

- these components shape the tone of multiple important pages
- they still mix Dutch with dramatic English/operator phrasing

Evidence:

- macro HUD:
  - [frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx:18)
  - [frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx:40)
  - [frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx:57)
  - [frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx:93)
  - [frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroTerminalHUD.jsx:106)
- report HUD:
  - [frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx:8)
  - [frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx:50)
  - [frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx:57)
  - [frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx:85)
  - [frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/report/ReportTerminalHUD.jsx:90)

Fix direction:

- remove “terminal theatre” copy where it no longer helps
- rewrite labels into clear product language
- move these shared components under dictionary-backed copy if they stay user-facing

#### 5. The FINN assistant overlay still contains large pockets of mixed language and internal action terminology

Why it matters:

- this is one of the most product-defining surfaces
- mixed language inside FINN undermines the credibility of all profile-aware work

Evidence:

- context labels and page map are still English:
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:379)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:389)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:396)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:403)
- error/fallback copy remains English:
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:3262)
- onboarding helper text inside FINN is mixed:
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:4262)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:4273)
- action labels and descriptions are hybrid:
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:4074)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:4154)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:5071)
  - [frontend/trading-tool-frontend/components/ui/AIAssistant.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/AIAssistant.jsx:5083)

Fix direction:

- treat FINN overlay as its own dedicated localization/polish project
- normalize all action labels, progress labels, states, and helper text
- reduce internal nouns like `Read-only`, `Setup Guide`, `Execution`, and mixed “review” phrasing unless intentionally chosen

### P2

#### 6. Admin pages are still clearly operator prototypes rather than polished product-ready admin surfaces

Why it matters:

- if these pages are reachable in live product, they reflect on product maturity too
- they currently sound like internal demos

Evidence:

- admin users:
  - [frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx:68)
  - [frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx:85)
  - [frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx:117)
  - [frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx:133)
- admin AI:
  - [frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx:90)
  - [frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx:132)
  - [frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx:164)
  - [frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/ai/page.jsx:220)
- admin logs:
  - [frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx:71)
  - [frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx:86)
  - [frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx:115)
  - [frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx:174)

Fix direction:

- decide whether admin stays operator-English or gets productized
- either hide these better from non-operators, or rewrite them intentionally as operational tools instead of “AI intelligence theatre”

#### 7. Bot flow still mixes polished Dutch product behavior with English proposals and form copy

Why it matters:

- bots are a major value surface
- mixed status/proposal/action copy weakens usability

Evidence:

- proposal notifications:
  - [frontend/trading-tool-frontend/app/(protected)/bot/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/bot/page.jsx:198)
  - [frontend/trading-tool-frontend/app/(protected)/bot/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/bot/page.jsx:201)
- mixed form and modal semantics:
  - [frontend/trading-tool-frontend/app/(protected)/bot/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/bot/page.jsx:211)
  - [frontend/trading-tool-frontend/app/(protected)/bot/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/bot/page.jsx:216)
- debug logging still visible in bot card:
  - [frontend/trading-tool-frontend/components/bot/BotAgentCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/BotAgentCard.jsx:117)

Fix direction:

- fully localize the bot action flow
- remove all shipped debug logging from bot surfaces

#### 8. Search, form, and table placeholders are still inconsistent across the product

Why it matters:

- these are frequent micro-interactions
- mixed placeholder language makes the product feel stitched together

## Residual Layer Found After Waves 1-3

After the first three polish waves, there is still a smaller but real residual layer left in older and deeper components.
This is no longer the big top-level product pass.
It is the "last 10-15%" cleanup layer that still matters before calling the frontend uniformly polished.

### Residual P1

#### 1. Older technical and market HUDs still contain internal English framing

Main leftovers:

- [frontend/trading-tool-frontend/components/technical/TechnicalTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/technical/TechnicalTerminalHUD.jsx:40)
- [frontend/trading-tool-frontend/components/market/MarketTerminalHUD.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/market/MarketTerminalHUD.jsx:41)

Examples:

- `Price Action Intelligence`
- `Technical Context`
- `Current Bias`
- `Execution Flow`
- `Dominant Trend`
- `Intelligence Consensus`
- `Market Bias`
- `Asset Tracking`
- `Live Feed`

Why it matters:

- these are still visually prominent shared surfaces
- the rest of the app is now much more product-like, so these older labels stand out harder

#### 2. Bot and governance surfaces still leak older English operator wording

Main leftovers:

- [frontend/trading-tool-frontend/components/bot/BotScores.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/BotScores.jsx:22)
- [frontend/trading-tool-frontend/components/bot/MarketDecisionCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/MarketDecisionCard.jsx:89)
- [frontend/trading-tool-frontend/components/bot/TradePlanCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/TradePlanCard.jsx:210)
- [frontend/trading-tool-frontend/components/bot/BotDecisionCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/BotDecisionCard.jsx:323)
- [frontend/trading-tool-frontend/app/(protected)/bot/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/bot/page.jsx:217)

Examples:

- `System Health & Market Scopes`
- `Market Context & Global Analysis`
- `Active Target Logic`
- `Market Price`
- `Risk Exposure`
- `Decision Review`
- `Plan Adherence`
- `Error generating proposal`

Why it matters:

- this is core product territory, not a hidden operator-only lane
- mixed wording here makes the product still feel half internal

#### 3. Some raw data tables still expose backend-style field names directly to users

Main leftover:

- [frontend/trading-tool-frontend/components/market/MarketForwardReturnTabs.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/market/MarketForwardReturnTabs.jsx:140)

Examples:

- `Node_Year`
- `Avg_Node`
- `Global_Avg`
- `Telemetry_Metric`
- `Node_Count`
- `Win_Events`
- `Loss_Events`
- `Success_Probability`

Why it matters:

- this is one of the clearest remaining “internal system leaking through UI” moments
- even strong copy elsewhere cannot offset raw schema labels shown directly in product tables

### Residual P2

#### 4. Profile, auth, and public entry flows still have scattered English leftovers

Main leftovers:

- [frontend/trading-tool-frontend/app/(protected)/profile/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/profile/page.jsx:587)
- [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:116)
- [frontend/trading-tool-frontend/app/(public)/register/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/register/page.jsx:53)

Examples:

- `Strategic Terminal Actions`
- `System-level intelligence settings`
- `Sign Out Securely`
- `user@example.com`
- `Your name`
- `Could not create the account. This email address may already exist.`

Why it matters:

- login/register/profile are identity surfaces
- small language breaks here feel more serious than in deep admin areas

#### 5. Several loaders, empty states, and helper labels are still in older English phrasing

Main leftovers:

- [frontend/trading-tool-frontend/components/ui/PageLoader.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/ui/PageLoader.jsx:6)
- [frontend/trading-tool-frontend/components/dashboard/GlobalMarketDecisionCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/dashboard/GlobalMarketDecisionCard.jsx:18)
- [frontend/trading-tool-frontend/components/bot/PortfolioBalanceCard.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/bot/PortfolioBalanceCard.jsx:292)
- [frontend/trading-tool-frontend/components/charts/TradingViewSmartChart.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/charts/TradingViewSmartChart.jsx:302)

Examples:

- `Loading Intelligent Dashboard…`
- `Syncing Global Market Telemetry...`
- `Syncing Terminal Data...`
- `No History Found`

Why it matters:

- these are small, but they show up exactly when the user is waiting or confused
- that makes them more noticeable than static headings

### Residual P3

#### 6. There is still production-noise logging on a number of user-facing paths

Main leftovers include:

- onboarding step completion logs on market, macro, technical, and setup pages
- multiple bot, strategy, setup, and assistant error logs
- a few fallback warnings in shared UI components

Representative locations:

- [frontend/trading-tool-frontend/app/(protected)/technical/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/technical/page.jsx:69)
- [frontend/trading-tool-frontend/app/(protected)/market/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/market/page.jsx:68)
- [frontend/trading-tool-frontend/app/(protected)/setup/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/setup/page.jsx:70)
- [frontend/trading-tool-frontend/app/(protected)/macro/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/macro/page.jsx:108)

Why it matters:

- most of these do not break the product
- but they keep the console noisy during QA and make genuine regressions harder to spot

## Suggested Next Cleanup Pass

If we want to continue immediately, the most efficient next pass is:

1. technical + market HUD localization
2. bot/governance wording cleanup
3. raw forward-return table labels
4. profile/login/register microcopy cleanup
5. loaders and production-noise console cleanup

Evidence:

- English search fields:
  - [frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/strategy/page.jsx:167)
  - [frontend/trading-tool-frontend/app/(protected)/setup/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/setup/page.jsx:127)
  - [frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/users/page.jsx:121)
  - [frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(protected)/admin/logs/page.jsx:179)
- English indicator searches:
  - [frontend/trading-tool-frontend/components/technical/TechnicalIndicatorScoreView.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/technical/TechnicalIndicatorScoreView.jsx:106)
  - [frontend/trading-tool-frontend/components/market/MarketIndicatorScoreView.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/market/MarketIndicatorScoreView.jsx:88)
  - [frontend/trading-tool-frontend/components/macro/MacroIndicatorScoreView.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/macro/MacroIndicatorScoreView.jsx:101)
- mixed auth/register placeholders:
  - [frontend/trading-tool-frontend/app/(public)/register/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/register/page.jsx:141)
  - [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:116)

Fix direction:

- do a global placeholder pass by surface language
- move placeholders into dictionaries where needed

### P3

#### 9. Dutch dictionary is improved, but still contains many loose English product nouns

Why it matters:

- the language layer is closer, but still not truly normalized
- future pages will keep drifting unless the dictionary is cleaned up centrally

Evidence:

- still mixed nouns:
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:18)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:31)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:54)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:119)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:129)
  - [frontend/trading-tool-frontend/dictionaries/nl.json](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/dictionaries/nl.json:226)

Fix direction:

- define a product noun table:
  - report / rapport
  - profile / profiel
  - setup / setup
  - strategy / strategie
  - dashboard / overzicht or dashboard
  - review / review or evaluatie
- then normalize dictionaries against that table

#### 10. Some remaining success/error copy is technically correct but still not product-grade

Why it matters:

- users feel this in toasts and edge states more than teams often expect
- it does not block release alone, but it prevents a truly finished feel

Evidence:

- mixed tone and language in notifications:
  - [frontend/trading-tool-frontend/components/NotificationToggle.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/NotificationToggle.jsx:56)
  - [frontend/trading-tool-frontend/components/NotificationToggle.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/components/NotificationToggle.jsx:57)
- mixed toast copy in auth:
  - [frontend/trading-tool-frontend/app/(public)/login/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/login/page.jsx:48)
  - [frontend/trading-tool-frontend/app/(public)/register/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/register/page.jsx:60)
  - [frontend/trading-tool-frontend/app/(public)/register/page.jsx](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/app/(public)/register/page.jsx:66)

Fix direction:

- do one dedicated snackbar/toast/empty/error microcopy pass after the bigger surface fixes

## Recommended Fix Order

### Wave 1

- remove mock/placeholder advice card
- finish strategy page localization
- finish report generation and PDF user copy
- remove shipped bot debug logs

### Wave 2

- rewrite macro HUD and report HUD
- normalize FINN assistant overlay labels, actions, and onboarding helper text
- unify placeholders and search fields

### Wave 3

- clean admin/operator surfaces intentionally
- normalize Dutch dictionary nouns centrally
- polish toasts, empty states, and edge-case feedback

## Readiness Verdict

- current full-product copy/polish readiness: `caution`
- core product readiness: `much improved`
- product-wide readiness for a “we checked everything” claim: `not yet`

## Definition Of Done For This Sweep

This audit is resolved when:

- no user-facing page still ships mock or placeholder business content
- no major flow visibly mixes Dutch and English by accident
- no shared HUD/card component still sounds like an internal demo
- FINN overlay reads consistently in one product voice
- admin surfaces are either intentionally operational or intentionally hidden
