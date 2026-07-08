# FINN Beta Architecture v1.0 Implementation Plan

Last updated: 2026-07-08

## Purpose

This document translates the locked FINN Beta Architecture v1.0 into an implementation-first migration plan.

This is not a new product concept.
This is the execution plan for:

- EPIC 1 — FINN Shell
- EPIC 2 — Asset Workspace

Guiding rule:

- move first
- keep existing business logic
- maximize reuse
- improve product hierarchy without a rebuild

## Scope lock

In scope:

- shell
- navigation
- routing behavior
- workspace composition
- onboarding handoff
- asset workspace composition

Out of scope:

- backend rewrite
- AI rewrite
- indicator expansion
- new analysis engine
- new workspaces beyond EPIC 1 and 2

## EPIC 0 Audit Summary

### Existing protected routes

- `/dashboard`
- `/market`
- `/macro`
- `/technical`
- `/setup`
- `/strategy`
- `/bot`
- `/report`
- `/profile`
- `/admin/*`

### Existing shell components

- `app/(protected)/layout.jsx`
- `components/ui/NavBar.jsx`
- `components/ui/TopBar.jsx`
- `components/ui/AIAssistant.jsx`
- `components/ui/AIFloatingButton.jsx`

### Existing asset-context building blocks

- `components/ui/AssetSearchBar.jsx`
- `hooks/useCurrentAsset.js`
- `app/(protected)/market/page.jsx`
- `app/(protected)/macro/page.jsx`
- `app/(protected)/technical/page.jsx`

### Directly reusable components

#### EPIC 1

- `AIAssistant`
- `NavBar`
- `TopBar`
- `AssetSearchBar`
- existing protected layout

#### EPIC 2

- `MarketTerminalHUD`
- `MarketIndicatorScoreView`
- `MarketSevenDayTable`
- `MarketForwardReturnTabs`
- `MacroTerminalHUD`
- `MacroIndicatorScoreView`
- `MacroTabs`
- `TechnicalTerminalHUD`
- `TechnicalIndicatorScoreView`
- `TechnicalTabs`
- `TechnicalTerminalGrid`
- `AgentInsightPanel`

### Components that primarily need repositioning

- current FINN assistant
- asset search
- market/macro/technical content blocks
- onboarding handoff

### Components that need real adaptation

- protected shell layout
- assistant layout mode
- navbar IA
- topbar context model
- route mapping for market/macro/technical

## EPIC 1 — FINN Shell

### Current state

The current app is platform-first:

- dashboard is the de facto home
- assistant opens as an overlay
- floating button is the assistant entry point
- page routing still defines the mental model

### Target state

The app becomes FINN-first:

- FINN is permanently visible
- the assistant is no longer opened or closed
- workspaces render in a central canvas
- dashboard stops acting like product home
- onboarding ends in FINN

### Execution approach

#### Phase 1

- keep existing routes
- convert assistant from overlay to persistent shell panel
- remove floating button entry pattern
- keep workspace pages rendering inside the protected shell

#### Phase 2

- adjust sidebar labels and hierarchy toward FINN-first wording
- use topbar as shell context layer
- route onboarding completion into FINN

#### Phase 3

- reduce dashboard-first language and positioning
- keep route compatibility while changing product framing

### Risks

- persistent assistant may still feel like a side panel if shell framing is too weak
- desktop/mobile layout balance can regress
- some handoff interactions currently assume closable assistant behavior

### Anti-regression rule

Do not change AI or business flows while changing shell placement.

## EPIC 2 — Asset Workspace

### Current state

Market, Macro, and Technical are separate routes and pages, but they all describe the same object:

- the active asset

### Target state

There is one Asset Workspace with tabs:

- Overview
- Market
- Macro
- Technical
- AI Analyse
- News later

Asset Search becomes the primary asset switch.

### Execution approach

#### Phase 1

- create one asset workspace container
- keep existing underlying content blocks
- introduce tab state at the workspace level

#### Phase 2

- map legacy routes to the correct asset workspace tab
- remove market/macro/technical from primary navigation

#### Phase 3

- strengthen the asset overview layer using existing components
- keep AI interpretation in FINN, not duplicated in workspace content

### Risks

- too much asset content can create a bloated first version
- legacy onboarding paths still point at old page routes
- overview can feel weak if it is only a wrapper around three old tabs

### Anti-regression rule

Do not rebuild analysis logic.
Only recompose existing modules under one asset object.

## Beta sequencing

### Week 1

- persistent FINN shell foundation
- remove floating button
- keep legacy routes working

### Week 2

- refine shell navigation and topbar context
- onboarding exits into FINN

### Week 3

- create asset workspace container
- wire legacy market/macro/technical into shared asset context

### Week 4

- add asset tab model
- map legacy routes to correct tabs

### Week 5

- polish shell hierarchy
- reduce dashboard-first product cues

### Week 6

- regression hardening
- beta QA
- final copy and usability pass

## Definition of success

The beta is successful when:

- FINN feels like the application
- the floating assistant pattern is gone
- users stay in one environment
- assets feel like objects, not datasets
- market/macro/technical are no longer primary destinations
- existing product logic still works
