# Agent Structure 3A Inventory

Status: reference
Date: 2026-08-09
Scope: inventory only, no cleanup applied

## Purpose

This document captures the `3A` inventory for the repository before any `3B` cleanup work begins.

It answers five questions:

1. how `docs/operations` currently breaks down
2. which generated or local artifacts are tracked in git
3. which duplicated static AI files appear to exist
4. whether `backend.db` and `backend/trading-tool-backend/package.json` are active dependencies
5. why deploy currently depends on `frontend/trading-tool-frontend/out`

## Executive Summary

The repository now has a clean root agent layer, but the operations layer is still dense and mixed-purpose.

Current inventory highlights:

- `docs/operations` contains `68` top-level files
- only `5` of those files are explicitly date-stamped historical artifacts
- the rest mix active runbooks, plans, checklists, roadmaps, audits, and summaries in one flat folder
- `frontend/trading-tool-frontend/out/` is a tracked deployment artifact, not just local build output
- backend vector-store code reads from `backend/static/ai/*`, while a second copy also exists under `backend/trading-tool-backend/backend/static/ai/*`
- `backend/trading-tool-backend/backend.db` is tracked, but no active code or docs in the current repo inventory depend on that exact file
- `backend/trading-tool-backend/package.json` appears orphaned from active backend workflows

## 1. Operations Document Inventory

### Current Shape

Observed at `docs/operations/`:

- total top-level files: `68`
- clearly date-stamped historical files: `5`

Pattern counts from filenames:

- `9` checklist files
- `9` plan files
- `4` roadmap files
- `4` audit files
- `2` status files
- `2` brief files
- `2` cutover files
- `1` runbook
- `1` playbook
- `1` handoff
- `1` inventory
- `1` release note
- `1` summary

### Recommended 3A Classification

This is an inventory classification only. Nothing has been moved or deleted.

#### Canonical candidates

These look closest to current normative references and should be considered first when `3B` chooses official sources:

- [environment-architecture.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/environment-architecture.md)
- [live-deploy-runbook.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/live-deploy-runbook.md)
- [platform-hardening-status.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-status.md)
- [platform-security-architecture-retest-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-security-architecture-retest-checklist.md)
- [staging-production-cutover-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/staging-production-cutover-checklist.md)

#### Active reference / planning documents

These appear useful, but not ideal as root source-of-truth documents:

- build-agent migration docs
- FINN roadmap docs
- sprint plans
- platform hardening tranche docs
- QA briefs and rerun playbooks
- certification push plan

#### Historical artifacts

These are useful evidence, but should not drive current workflows directly:

- [finn-runtime-architecture-audit-2026-07-20.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-runtime-architecture-audit-2026-07-20.md)
- [oracle-staging-to-production-cutover-2026-06-07.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/oracle-staging-to-production-cutover-2026-06-07.md)
- [product-polish-audit-2026-06-24.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/product-polish-audit-2026-06-24.md)
- [product-wide-ui-copy-audit-2026-06-24.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/product-wide-ui-copy-audit-2026-06-24.md)
- [finn-trader-profile-release-note-2026-06-23.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-trader-profile-release-note-2026-06-23.md)

### 3A Conclusion

`docs/operations` is not yet structurally wrong, but it is still too flat and too mixed for long-term agent use.

The main `3B` document task should be:

- keep a very small canonical set
- demote the rest to reference or historical status
- replace overlap with links, not duplicate instructions

## 2. Tracked Generated And Local Artifacts

### Frontend Export

Tracked files under `frontend/trading-tool-frontend/out/`:

- tracked file count: `142`

This directory currently includes:

- static HTML exports
- `_next/static` build output
- generated JS/CSS chunks
- app route exports
- icons, manifest, worker assets
- screenshot-like assets such as `dashboard_mockup.png`

### Backend / AI Artifacts

Tracked local or generated-looking artifacts include:

- [backend/static/ai/semantic_index.faiss](/Users/gvangalen/Documents/antigravity-trading-tool/backend/static/ai/semantic_index.faiss)
- [backend/static/ai/vector_mapping.json](/Users/gvangalen/Documents/antigravity-trading-tool/backend/static/ai/vector_mapping.json)
- [backend/trading-tool-backend/backend/static/ai/semantic_index.faiss](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/static/ai/semantic_index.faiss)
- [backend/trading-tool-backend/backend/static/ai/vector_mapping.json](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/static/ai/vector_mapping.json)
- [backend/trading-tool-backend/backend.db](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend.db)

### 3A Conclusion

The repo currently tracks both:

- deployment artifacts
- local/generated data artifacts

This is workable, but it makes source-of-truth boundaries blurry.

## 3. Duplicate AI Static Directories

### Observed Duplication

Two parallel AI-static locations are tracked:

- [backend/static/ai](/Users/gvangalen/Documents/antigravity-trading-tool/backend/static/ai)
- [backend/trading-tool-backend/backend/static/ai](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/static/ai)

### Verified Runtime Read Path

The active vector-store path is hardcoded in [vector_store.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/vector_store.py:15):

- `INDEX_PATH = "backend/static/ai/semantic_index.faiss"`
- `MAPPING_PATH = "backend/static/ai/vector_mapping.json"`

That points to the root-level backend static directory, not the nested mirror.

### 3A Conclusion

Based on the currently verified runtime code:

- `backend/static/ai/*` looks like the active runtime path
- `backend/trading-tool-backend/backend/static/ai/*` looks like a duplicate mirror or stale carry-over

`3B` should confirm whether any scripts still write to the nested copy before consolidation.

## 4. backend.db Inventory

Tracked file:

- [backend.db](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend.db)

### Observed Usage

During this inventory pass:

- no active code reference was found that explicitly depends on `backend/trading-tool-backend/backend.db`
- the backend README mentions a SQLite example `sqlite:///market_data.db`, not `backend.db`

### 3A Conclusion

`backend.db` currently looks like a local or legacy data artifact, not a verified production dependency.

It should be treated as suspicious until proven otherwise.

`3B` should decide whether it becomes:

- ignored local state
- archived sample data
- or a documented fixture

## 5. backend/trading-tool-backend/package.json Inventory

Current contents:

- only `react-hot-toast` as a dependency

Tracked neighbors:

- [backend/trading-tool-backend/package.json](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/package.json)
- [backend/trading-tool-backend/package-lock.json](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/package-lock.json)

### Observed Usage

During this inventory pass:

- no backend workflow, docs reference, or runtime script was found that uses this package manifest
- `react-hot-toast` is actively used by the frontend, not by backend Python code
- backend dependency installation is driven by Python requirements, not by this Node manifest

### 3A Conclusion

This package manifest currently looks orphaned or accidental.

It should not be removed during `3A`, but it is a strong `3B` cleanup candidate unless a hidden workflow still depends on it.

## 6. Why Deploy Depends On out/

This dependency is explicit and current.

### GitHub Workflow Gate

[deploy.yml](/Users/gvangalen/Documents/antigravity-trading-tool/.github/workflows/deploy.yml:34) verifies that if frontend source changed, tracked export files changed too.

### Remote Deploy Script

[deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh:169) refuses deployment if `out/index.html` is missing.

It also:

- skips server-side frontend build
- uses the prebuilt export committed in git
- preserves previous `_next/static` chunks for already-open browsers

### Rollback Script

[rollback_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/rollback_env.sh:66) also refuses rollback if `out/index.html` is missing.

### Next.js Config

[next.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend/next.config.js:5) sets:

- `output: 'export'`

That means this frontend is intentionally built as a static export artifact.

### 3A Conclusion

Deploy depends on `out/` because the current production model is:

- build frontend locally or in CI
- commit the static export into git
- deploy the committed export
- do not rebuild frontend on the server

This is not accidental. It is part of the current release architecture.

## 7. 3A Decision Log

No cleanup was applied during this phase.

No files were deleted, moved, or reclassified in place.

The inventory supports the following `3B` candidates:

1. document status tagging for `docs/operations`
2. consolidation of duplicated AI static directories
3. decision on whether `backend.db` should remain tracked
4. decision on whether backend Node package files should remain tracked
5. explicit artifact policy for `frontend/trading-tool-frontend/out`

## Recommended Next Step

Proceed to `3B` only after choosing policy for these items:

- Is `out/` still intended to stay committed long-term?
- Which `docs/operations` files become canonical, reference, or historical?
- Is `backend/static/ai/` the only approved runtime location?
- Is `backend.db` allowed in git?
- Is `backend/trading-tool-backend/package.json` intentionally retained?
