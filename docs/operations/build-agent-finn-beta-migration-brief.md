# Build Agent Brief — FINN Beta Migration (EPIC 1 & 2)

Last updated: 2026-07-08

## Purpose

Read this before starting implementation.

This document is the execution brief for the agreed FINN beta migration.
The product direction is already decided.
Do not redesign it.
Do not expand scope.

Your job is to implement the agreed architecture as simply, safely, and maintainably as possible.

## Goal

We are not building a new product.

We are migrating the existing application so that:

- FINN feels like the application
- FINN is no longer a popup or overlay
- workspaces load inside the FINN Shell
- existing business logic stays intact
- existing components are reused as much as possible

## Scope

Only build:

- EPIC 1 — FINN Shell
- EPIC 2 — Asset Workspace

Out of scope:

- My Plan migration
- Automation migration
- Reflection migration
- AI rewrites
- backend rewrites
- new indicators
- new analysis engines
- new business logic

## Architectural rule

From now on we build:

- FINN Shell
- Workspaces
- Modules

We do not build new standalone pages as new product concepts.

## Core philosophy

FINN is the operating layer.

Workspace = facts, controls, and data.
FINN = meaning, coaching, and next step.

Do not duplicate workspace information inside FINN.
FINN should interpret what the workspace means for this user.

## Build principle

Always follow this order:

1. move
2. make it work
3. improve

Do not:

1. redesign
2. rebuild
3. then integrate

New components should only be created when existing components are clearly not suitable.

## EPIC 1 — FINN Shell

### Goal

Make FINN the permanent environment of the application.

The user should no longer:

- open FINN
- close FINN
- treat FINN like an overlay

Instead:

- FINN stays visible
- the central workspace changes
- the user remains inside one FINN environment

### What must be built

#### 1. Protected shell becomes the FINN Shell

Use the existing protected layout as the base.

The shell should contain:

- sidebar
- topbar
- workspace canvas
- permanent FINN panel

#### 2. Remove the floating assistant pattern

Remove the floating button as the primary entry pattern.

Remove overlay behavior as the main assistant model.

FINN should not feel like a popup.

#### 3. Make `AIAssistant` shell-compatible

Use the existing `AIAssistant` component.

Adapt it for shell mode:

- persistent rendering
- no close button in shell mode
- no overlay positioning in shell mode
- no open/close mental model as primary interaction

#### 4. FINN becomes product home

For beta, the underlying route may still temporarily remain `dashboard` if needed for compatibility.

But product behavior must make it feel like:

- FINN is home
- dashboard is not presented as the product start

#### 5. Sidebar supports shell hierarchy

The shell navigation should reinforce that FINN is the app.

At minimum:

- FINN should be the clear home label
- old page-based logic should stop being emphasized as the primary product mental model

#### 6. Topbar becomes shell context

Topbar should show:

- active context
- global asset search
- account/avatar

Do not make topbar reinforce old page-thinking more than necessary.

#### 7. Asset Search belongs to the shell

Use the existing `AssetSearchBar` as a global shell control.

It should not behave like a local page-only widget.

#### 8. Onboarding ends in FINN

After onboarding, the user must enter the protected FINN shell.

Not the public landing.
Not a dashboard-first feeling.

#### 9. Legacy routes continue to work

These routes may remain for now:

- `/dashboard`
- `/market`
- `/macro`
- `/technical`
- `/setup`
- `/strategy`
- `/bot`
- `/report`

But they must render inside the same shell.

### Practical shell model

Desktop and app must be the same product.

Only responsive behavior may change.

Do not invent a separate mobile architecture.

Mental model:

- one shell
- one product hierarchy
- same logic on desktop and app
- only stacking and sizing differ

## EPIC 2 — Asset Workspace

### Goal

Market, Macro, and Technical become one product:

- Asset Workspace

The user should think:

- "I am viewing BTC"

Not:

- "I am opening Macro"

### Asset Workspace structure

- Overview
- Market
- Macro
- Technical
- AI Analyse
- News later

Do not build News now.

### What must be built

#### 1. Asset Workspace container

Build one workspace container for asset context.

Do not build a new analysis engine.
Reuse the current content.

#### 2. Asset Search is the primary asset switch

Flow:

- user searches `BTC`
- active asset changes
- Asset Workspace shows `BTC`

Do not require the user to pick a dataset page first.

#### 3. Reuse existing Market/Macro/Technical content

Use existing content from:

- `market/page`
- `macro/page`
- `technical/page`

And their supporting components.

#### 4. Use one shared asset context

Market, Macro, and Technical must share the same active asset context.

They should not feel like three separate page contexts anymore.

#### 5. Keep legacy routes temporarily

Legacy routes stay alive for compatibility, but should internally open the correct Asset Workspace tab:

- `/market?symbol=BTC` → Asset Workspace / Market
- `/macro?symbol=BTC` → Asset Workspace / Macro
- `/technical?symbol=BTC` → Asset Workspace / Technical

#### 6. Keep AI Analyse minimal

Do not create new AI systems.

If an AI Analyse tab is needed in beta:

- reuse existing FINN/insight framing
- keep it lightweight

### Reuse-first component strategy

Directly reusable:

- `AIAssistant`
- `NavBar`
- `TopBar`
- `AssetSearchBar`
- protected layout
- current asset hooks/state
- current market/macro/technical component stacks

Mostly move/recompose:

- market HUD/content
- macro HUD/content
- technical HUD/content
- insight panels
- asset tables/tabs/config views

Needs real adaptation:

- protected shell layout
- assistant shell mode
- sidebar hierarchy
- topbar context model
- route mapping toward asset workspace tabs
- onboarding handoff

## What not to do

Do not:

- propose a new architecture
- add new workspaces now
- rewrite AI logic
- rewrite backend logic
- add new analysis features
- redesign business flows
- expand product scope

If you notice future improvements:

- note them separately as feedback
- do not change scope in this beta implementation

## Recommended implementation order

### Phase 1 — Shell foundation

- convert protected layout into shell
- render FINN persistently
- remove floating button
- remove overlay behavior

### Phase 2 — Shell behavior

- make topbar shell-context aware
- keep asset search in shell
- make FINN the product home
- route onboarding into FINN shell

### Phase 3 — Asset Workspace foundation

- create asset workspace container
- centralize asset context
- embed market/macro/technical content as tabs or sub-sections

### Phase 4 — Legacy compatibility

- route legacy market/macro/technical URLs to correct asset workspace tabs
- reduce regressions

### Phase 5 — Polish

- tidy copy
- improve responsive shell behavior
- stabilize state continuity

## Success criteria

The beta is successful when:

- FINN feels like the application
- the user understands within 30 seconds what FINN is
- the user no longer wonders where to begin
- the floating button is gone
- dashboard is not the product home
- market, macro, and technical are no longer separate primary destinations
- asset search opens one unified asset context
- existing functionality largely remains intact
- the codebase is simpler structurally than before
- future workspaces can be added to the shell cleanly

## Definition of done

### EPIC 1 is done when

- protected shell exists
- FINN is permanently visible
- floating button is removed
- overlay behavior is removed as primary interaction
- onboarding ends in the FINN shell
- legacy routes still work inside the shell

### EPIC 2 is done when

- one Asset Workspace exists
- Market/Macro/Technical live inside it
- asset search switches the active asset context
- legacy routes open the correct asset tab
- no new analysis engine has been built

## First concrete implementation tasks

### Task 1

- make `AIAssistant` shell-compatible
- render FINN persistently in protected layout
- remove `AIFloatingButton`
- stop using overlay open/close as primary behavior

### Task 2

- route onboarding completion into the protected shell
- make the shell feel like FINN home

### Task 3

- create Asset Workspace container
- mount current market/macro/technical content into it
- wire global asset search into shared asset context

### Task 4

- add legacy route mapping from market/macro/technical to the correct asset workspace tab

## Final reminder

Do not build new functionality.

Restructure the current functionality.

That is the assignment.
