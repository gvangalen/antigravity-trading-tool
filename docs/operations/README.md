# Operations Index

Status: canonical

## Purpose

This index classifies the current `docs/operations/` folder so agents and contributors can distinguish:

- canonical operations references
- active reference material
- historical artifacts
- data assets such as QA promptsets

This file does not replace the root agent layer in `AGENTS.md`. It only organizes the operations layer beneath it.

## Canonical References

Use these first when the question is operational, architectural, release-related, or platform-hardening related:

- [environment-architecture.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/environment-architecture.md)
- [live-deploy-runbook.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/live-deploy-runbook.md)
- [platform-hardening-status.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-status.md)
- [platform-security-architecture-retest-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-security-architecture-retest-checklist.md)
- [staging-production-cutover-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/staging-production-cutover-checklist.md)
- [finn-qa-fixture-contract.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-fixture-contract.md)
- [finn-authenticated-runtime-gate.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-authenticated-runtime-gate.md)

## Active Reference Material

These documents remain useful, but should not be treated as root source-of-truth unless explicitly linked from a canonical reference:

### Build / migration

- `build-agent-finn-beta-*`
- `finn-beta-architecture-v1-implementation-plan.md`

### QA / release

- `finn-4-performance-intelligence-qa.md`
- `finn-5-governance-qa.md`
- `finn-qa-*`
- `finn-trader-profile-qa-brief.md`
- `platform-hardening-phase6-qa.md`

### Roadmaps / planning

- `finn-roadmap-v2.md`
- `finn-roadmap-v3.md`
- `finn-roadmap-v4.md`
- `finn-roadmap-v5-discovery-architecture.md`
- `finn-stable-next-plan.md`
- `overview-market-performance-long-term-plan.md`
- `product-go-live-polish-plan.md`
- `testing-blind-spots-and-improvement-plan.md`

### Platform hardening slices

- `platform-hardening-next-plan.md`
- `platform-hardening-step*.md`
- `platform-hardening-tranche-*.md`
- `platform-phase-2-1-*.md`
- `platform-scale-*.md`
- `replay-exactly-once-inventory.md`
- `security-hardening-phase1.md`

## Historical Artifacts

These are useful evidence but should be treated as historical context rather than current workflow authority:

- [finn-runtime-architecture-audit-2026-07-20.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-runtime-architecture-audit-2026-07-20.md)
- [oracle-staging-to-production-cutover-2026-06-07.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/oracle-staging-to-production-cutover-2026-06-07.md)
- [product-polish-audit-2026-06-24.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/product-polish-audit-2026-06-24.md)
- [product-wide-ui-copy-audit-2026-06-24.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/product-wide-ui-copy-audit-2026-06-24.md)
- [finn-trader-profile-release-note-2026-06-23.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-trader-profile-release-note-2026-06-23.md)

## Repository Restructuring Notes

These are useful repository-maintenance records, but they are not enduring operational source-of-truth documents:

- [agent-structure-3a-inventory-2026-08-09.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/agent-structure-3a-inventory-2026-08-09.md)
- [agent-structure-3b-cleanup-2026-08-09.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/agent-structure-3b-cleanup-2026-08-09.md)

## Data Assets

These are machine-readable or suite-input artifacts:

- `finn-qa-promptset-full.json`
- `finn-qa-promptset-governance.json`
- `finn-qa-promptset-performance-intelligence.json`

## Artifact Policy

Current repository policy after `3B`:

- `frontend/trading-tool-frontend/out/` is a tracked deployment artifact
- generated frontend export files are not contract authority for code review or API review
- `backend/static/ai/` is the currently verified runtime vector-store path
- nested duplicate AI static files under `backend/trading-tool-backend/backend/static/ai/` are not yet consolidated
- `backend/trading-tool-backend/backend.db` should not be newly tracked
- other local backend DB filenames are not yet covered by `.gitignore` and still require explicit cleanup policy if they appear

## Deferred Cleanup

The following items remain intentionally deferred because they need a separate safety decision:

- consolidation or deletion of duplicated AI static directories
- any change to the tracked frontend export deployment model
- any migration of current operations documents into subfolders
