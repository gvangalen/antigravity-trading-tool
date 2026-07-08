# Build Start Order — FINN Beta Migration

Last updated: 2026-07-08

## Purpose

This is the literal start order for the Build Agent.

Read together with:

- `docs/operations/build-agent-finn-beta-migration-brief.md`
- `docs/operations/build-agent-finn-beta-checklist.md`

Do not reinterpret the product direction.
Do not expand scope.

## Start Order

### 1. Freeze scope before coding

Confirm in your own notes that this pass only covers:

- EPIC 1 — FINN Shell
- EPIC 2 — Asset Workspace

Do not build:

- My Plan
- Automation
- Reflection
- new AI behavior
- new backend logic
- new indicators
- new analysis engines

### 2. Audit current reusable components

Inspect and reuse first:

- protected layout
- `AIAssistant`
- `NavBar`
- `TopBar`
- `AssetSearchBar`
- current market page/content
- current macro page/content
- current technical page/content
- current asset hooks/state

Only create new components when composition is clearly cleaner than copying page logic.

### 3. Make the protected layout the FINN Shell

Convert the existing protected app layout into one shell with:

- sidebar
- topbar
- central workspace canvas
- persistent FINN panel

Desktop and app are the same product.
Only stacking, sizing, and responsive layout may differ.

### 4. Make FINN persistent

Adapt the existing `AIAssistant` for shell mode:

- render persistently
- no close button in shell mode
- no floating assistant as primary interaction
- no overlay-first user model

Remove the floating assistant button from the protected shell.

### 5. Make FINN feel like product home

Update shell labels and onboarding completion so the user lands in the protected FINN environment.

The user should feel:

- FINN is home
- work happens inside FINN
- dashboard is not the primary product concept

### 6. Create Asset Workspace

Create one Asset Workspace container with these tabs:

- Overview
- Market
- Macro
- Technical
- AI Analyse

Do not build News now.

Reuse current Market/Macro/Technical content inside this workspace.

### 7. Wire asset context once

Make Asset Search open one asset context.

Expected behavior:

- user searches `BTC`
- app opens the Asset Workspace for `BTC`
- Market/Macro/Technical use the same active asset

Do not let each old page silently own a different asset context.

### 8. Preserve legacy routes

Keep existing routes working, but route them into the Asset Workspace:

- `/market?symbol=BTC` opens Asset Workspace / Market
- `/macro?symbol=BTC` opens Asset Workspace / Macro
- `/technical?symbol=BTC` opens Asset Workspace / Technical

Do not break old links during this beta migration.

### 9. Run focused verification

Before reporting done, verify:

- `npm run test:i18n`
- `npm run build`
- `/dashboard` renders in FINN Shell
- `/market?symbol=BTC` opens Market tab
- `/macro?symbol=BTC` opens Macro tab
- `/technical?symbol=BTC` opens Technical tab
- Asset Search opens the Asset Workspace
- onboarding completion lands in the protected FINN environment

### 10. Report exactly what changed

Final report must include:

- files changed
- tests/build status
- what is done for EPIC 1
- what is done for EPIC 2
- known blockers or deferred work

Do not claim My Plan, Automation, Reflection, or future workspace migrations are done.
