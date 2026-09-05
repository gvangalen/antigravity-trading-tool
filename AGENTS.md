# AGENTS.md

Status: canonical

## Purpose

This repository contains the Tradamind product across four active surfaces:

- backend: FastAPI application, services, background jobs, tests
- frontend: Next.js web application
- mobile: Expo / React Native client
- ops: deploy scripts, environment bootstrap, runtime operations notes

This file is the root control layer for agent-led work in this repository.

## Active Agents

- Build: implements approved changes and runs targeted basic validation
- QA: independently evaluates behavior, regressions, acceptance, and general code quality
- Security: independently evaluates security correctness, safety controls, exposure, and abuse paths
- Architecture: independently evaluates boundaries, dependencies, data flow, scalability, and operational fit

Review is not a separate role in this repository. General code review belongs to QA. Security-specific review belongs to Security.

## Source Of Truth Order

When instructions disagree, use this order:

1. the user request and explicit task scope
2. this `AGENTS.md`
3. canonical files under `docs/agents/`
4. actual code, package scripts, test configuration, and workflows present in the repository
5. canonical product and operational documentation
6. historical audits, handoffs, and legacy checklists

Conflict rule:

- If canonical documentation does not match the current code or configuration, do not invent commands or assumptions.
- Report the mismatch.
- Use only commands and paths that are verifiably present.
- Update documentation only when that is within the task scope.

## Agent Rights

- Build: may modify code and repository files within the approved task scope
- QA: read-only by default; may add or change tests only when explicitly requested
- Security: read-only by default; may apply fixes only when explicitly requested
- Architecture: read-only by default; may apply refactors only when explicitly requested

## Risk-Guided Engagement Matrix

| Change type | Build | QA | Security | Architecture |
| --- | --- | --- | --- | --- |
| Small UI or copy fix | Yes | Targeted check | No | No |
| Functional change | Yes | Yes | If relevant | If structural |
| Auth, actions, secrets, exposure | Yes | Yes | Yes | If structural |
| New service, queue, data flow, storage contract | Yes | Yes | Yes | Yes |
| Audit or assessment only | No | Per request | Per request | Per request |

## Standard Workflow

1. Read the user request and determine the active role or roles.
2. Read this file and the relevant file under `docs/agents/`.
3. Verify the real repository entry points before relying on documentation.
4. Perform only the work allowed by the active role and task scope.
5. Run only the validation that is actually defined and available.
6. Report findings, gaps, and mismatches in the role's required output format.

## FINN Release Read Routes

For FINN work, these documents are mandatory in addition to the applicable
role document. A loose task may narrow implementation scope, but may not
silently replace this release process.

- Build reads `docs/agents/build.md`, `docs/agents/FINN_RELEASE_PROCESS.md`,
  `docs/agents/FINN_RELEASE_STATUS.md`, and the explicitly active goal before
  making FINN changes.
- QA reads `docs/agents/qa.md`, `docs/agents/FINN_RELEASE_PROCESS.md`,
  `docs/agents/FINN_RELEASE_STATUS.md`, and the explicit QA goal before a
  production QA run.
- Security and Architecture retain their existing read-only responsibilities
  unless the user explicitly grants implementation authority.
- Only the goal explicitly identified by the current user task is active.
  Historical goals, handoffs, and reports may supply context but cannot define
  current FINN release or QA status.

## Stop And Escalate

Stop and report when any of the following is true:

- the requested change conflicts with explicit task scope
- the documented workflow conflicts with repository reality
- a required command or script does not exist
- the task would require a role to exceed its default modification rights
- there is an unresolved high-risk ambiguity involving auth, secrets, execution safety, or production behavior

## FINN Role Boundaries

`docs/agents/FINN_RELEASE_PROCESS.md` is the sole detailed FINN release flow;
`docs/agents/FINN_RELEASE_STATUS.md` is the sole current FINN release and QA
status source.

- Build completes one coherent local repair batch, verifies it, manages the
  candidate, CI, deployment, and bounded live smoke, and records only measured
  evidence in the status file. Its authenticated smoke uses only the canonical
  Build smoke fixture and generic non-sealed cases. It must not start,
  instruct, contact, poll, or otherwise coordinate a QA agent, access the QA
  fixture, or read the QA-exclusive sealed holdout.
- QA is an independent, read-only final gate for the exact live SHA in the
  status file. QA completes the prescribed matrix even when individual content
  cases fail, subject only to each case's hard timeout and the run's wall-clock
  limit. The sealed holdout is QA-exclusive and QA may use it only unchanged.
  QA records one evidence-backed verdict and does not repair code, deploy, or
  direct another agent.
- The user alone initiates QA after the status file reaches
  `READY_FOR_INDEPENDENT_QA`. A QA verdict never starts another Build or QA
  cycle automatically.
- Neither role may call a release green, live, or accepted without the
  corresponding measured evidence recorded in the status file. Build cannot
  accept its own release, lower QA thresholds, or alter rollback markers.

## Repository Reality Notes

These current constraints are verified from the repository and should be treated as real until changed in code:

- root `pytest -q` is configured for `backend/trading-tool-backend/backend/tests` via `pytest.ini`
- frontend has canonical `build`, `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, and `audit:high` scripts
- mobile has canonical `typecheck`, `lint`, `smoke:web`, `smoke:ios`, `smoke:android`, plus interactive Expo start commands
- mobile lint warnings are currently visible but do not fail the quality gate unless Expo reports lint errors
- `smoke:web` validates only the web bundle path
- `smoke:ios` and `smoke:android` validate Expo platform bundles only, not native Xcode/Gradle builds or store archives
- GitHub Actions now contains separate `ci.yml` and `deploy.yml` workflows

## Canonical Agent Docs

- `docs/agents/build.md`
- `docs/agents/qa.md`
- `docs/agents/security.md`
- `docs/agents/architecture.md`

## Non-Goals For This Layer

This control layer does not itself:

- create missing scripts
- redefine CI behavior
- replace detailed operational runbooks
- auto-resolve documentation drift

Those changes require explicit implementation work.
