# Agent Structure 3B Cleanup

Status: reference
Date: 2026-08-09

## Purpose

This document records the cleanup actions applied in `3B` after the repository inventory.

## Applied Changes

### 1. Operations layer now has a canonical index

Added:

- [README.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/README.md)

Effect:

- establishes a canonical entry point for the mixed `docs/operations/` folder
- separates canonical, active reference, historical, and data-asset documents
- reduces ambiguity without moving or deleting historical planning material

### 2. Local backend DB artifact is now explicitly ignored

Updated:

- [.gitignore](/Users/gvangalen/Documents/antigravity-trading-tool/.gitignore)

Effect:

- prevents new accidental tracking of `backend/trading-tool-backend/backend.db`
- aligns repository policy with the `3A` finding that this file is not a verified runtime dependency

### 3. Clearly orphaned backend Node manifest files were removed

Removed:

- [backend/trading-tool-backend/package.json](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/package.json)
- [backend/trading-tool-backend/package-lock.json](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/package-lock.json)

Reason:

- no active backend workflow, runtime path, or docs reference used them
- the manifest only carried `react-hot-toast`, which belongs to frontend usage
- backend dependency management in this repo is Python-based

### 4. Empty tracked backend DB artifact was removed

Removed:

- [backend.db](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend.db)

Reason:

- tracked size was `0B`
- no active repository reference was found for this exact file
- retaining it as tracked state increased ambiguity without verified value

## Deferred Items

The following cleanup candidates were intentionally not applied in `3B`:

### Duplicate AI static directories

Reason for deferral:

- the two directories do not match in size or contents
- active runtime reads from `backend/static/ai/`
- deleting the nested mirror without provenance confirmation is higher risk than leaving it documented for now

Deferred paths:

- [backend/static/ai](/Users/gvangalen/Documents/antigravity-trading-tool/backend/static/ai)
- [backend/trading-tool-backend/backend/static/ai](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/static/ai)

### Tracked frontend export model

Reason for deferral:

- deploy and rollback explicitly require committed `out/index.html`
- changing this would be a release-architecture decision, not a cleanup-only edit

Deferred path:

- [frontend/trading-tool-frontend/out](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/out)

## Result

`3B` reduced low-value repository ambiguity without changing the live deployment model or touching higher-risk runtime assets.
