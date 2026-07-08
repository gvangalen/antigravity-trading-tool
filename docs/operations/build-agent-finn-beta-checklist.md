# Build Agent Checklist — FINN Beta (EPIC 1 & 2)

Last updated: 2026-07-08

## Read first

Read this together with:

- `docs/operations/build-agent-finn-beta-migration-brief.md`

This checklist is the short execution version.

## Non-negotiables

- Do not redesign the product direction.
- Do not expand scope.
- Do not build new AI or backend logic.
- Do not add new analysis features.
- Reuse existing components by default.

## Core product rule

FINN is the application.

Not:

- a popup
- an overlay
- a side assistant on top of the app

Yes:

- one FINN Shell
- workspaces inside the shell
- modules inside workspaces

## Desktop and app rule

Desktop and app must be the same product.

That means:

- same shell
- same hierarchy
- same navigation logic
- same workspace model

Only this may differ:

- responsive layout
- stacking
- sizing

Do not invent a separate mobile architecture.

## Scope

Build only:

- EPIC 1 — FINN Shell
- EPIC 2 — Asset Workspace

Do not build now:

- My Plan migration
- Automation migration
- Reflection migration

## EPIC 1 checklist

### Shell foundation

- [ ] Protected layout behaves like one FINN Shell
- [ ] FINN is permanently visible in the shell
- [ ] Floating button is removed
- [ ] Overlay assistant pattern is removed as the main interaction

### Shell behavior

- [ ] FINN feels like home
- [ ] Dashboard is no longer presented as product-home
- [ ] Topbar behaves like shell context, not page context
- [ ] Asset Search lives in the shell
- [ ] Onboarding ends in the FINN shell

### Compatibility

- [ ] Legacy routes still render inside the shell
- [ ] Existing business logic still works

## EPIC 2 checklist

### Asset Workspace

- [ ] One Asset Workspace container exists
- [ ] It contains:
  - Overview
  - Market
  - Macro
  - Technical
  - AI Analyse
- [ ] News is not built now

### Asset switching

- [ ] Asset Search is the main way to switch asset context
- [ ] Asset Workspace updates when active asset changes
- [ ] Market/Macro/Technical share one asset context

### Legacy compatibility

- [ ] `/market` opens Asset Workspace / Market
- [ ] `/macro` opens Asset Workspace / Macro
- [ ] `/technical` opens Asset Workspace / Technical

## Reuse-first checklist

- [ ] Existing `AIAssistant` reused
- [ ] Existing `NavBar` reused/adapted
- [ ] Existing `TopBar` reused/adapted
- [ ] Existing `AssetSearchBar` reused
- [ ] Existing market components reused
- [ ] Existing macro components reused
- [ ] Existing technical components reused

## Do not rebuild

- [ ] No new AI engine
- [ ] No backend rewrite
- [ ] No new indicators
- [ ] No new analysis engine
- [ ] No new standalone product concept

## Build order

### First

- [ ] Make assistant shell-compatible
- [ ] Render FINN persistently in protected layout
- [ ] Remove floating button and overlay-first pattern

### Second

- [ ] Route onboarding into shell
- [ ] Make FINN the product-home experience

### Third

- [ ] Build Asset Workspace container
- [ ] Mount existing Market/Macro/Technical content into it

### Fourth

- [ ] Add legacy route mapping to correct asset tabs

### Fifth

- [ ] Polish layout
- [ ] Reduce regressions
- [ ] Verify responsive behavior for desktop and app

## Done when

- [ ] FINN feels like the application
- [ ] Desktop and app follow the same product model
- [ ] User no longer has to think where to start
- [ ] Asset context is unified
- [ ] Existing functionality remains mostly intact
