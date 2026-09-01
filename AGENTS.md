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

## Stop And Escalate

Stop and report when any of the following is true:

- the requested change conflicts with explicit task scope
- the documented workflow conflicts with repository reality
- a required command or script does not exist
- the task would require a role to exceed its default modification rights
- there is an unresolved high-risk ambiguity involving auth, secrets, execution safety, or production behavior

## Build Agent Contract

The following rules bound Build-to-QA handoffs for every explicit build
assignment. They do not grant Build independent acceptance authority.

- Build may make at most one QA handoff for an explicit build assignment.
- Build may hand off to QA only after its required tests, CI, deployment, and
  production-SHA verification have completed successfully.
- After the handoff, Build may perform at most one status check of the QA
  task. It must not poll, wait, or remain active indefinitely for QA.
- After that status check, Build must finish its own task with
  `WAITING_FOR_INDEPENDENT_QA` until the user provides a new explicit
  instruction.
- Build must not start a new build or repair round from a QA result. For a
  `NOT ACCEPTED` result, it may record only the verdict and report reference.
- A new explicit user instruction is required before Build changes code after
  either QA verdict. An `ACCEPTED` verdict must not trigger a second QA run.
- Build must not accept its own release, alter QA thresholds, update a rollback
  marker, or create a Build-to-QA ping-pong chain.

## QA Agent Contract

The following rules preserve independence and bound each QA assignment.

- QA may run at most one independent QA run for each supplied production SHA.
- QA must return only its verdict and fault batch; it must not instruct Build
  to repair findings or begin a new build round.
- QA ends its task after either `ACCEPTED` or `NOT ACCEPTED`. It must not run
  QA again for the same SHA, or accept a new production SHA in the same run,
  without a new explicit user instruction.
- QA must not wait indefinitely for processes, workers, threads, runtime calls,
  or another agent.
- Every individual provider, runtime, or harness case has a hard timeout. A
  nonterminal case at that boundary is recorded as a lifecycle failure.
- A case may have at most one bounded retry, and only for an evidenced
  infrastructure failure. Content failures have no retry.
- A definitive hard acceptance-gate failure cannot become green later in the
  same QA run. QA may then perform only pre-agreed, safe diagnostics for at
  most 30 additional minutes.
- A complete independent production QA run has a 120-minute wall-clock limit,
  unless the explicit QA assignment sets another total limit. On expiry QA
  stops and reports the run as incomplete or `NOT ACCEPTED`, based on the
  evidence collected.
- Where the assignment supplies no stricter case limit, an interactive runtime
  case has a five-minute hard timeout. Waiting for another agent never extends
  a case or run timeout.

## Build To QA Cycle

Every transition from `NOT ACCEPTED` to a new build round requires a new
explicit user instruction. Every transition from a new build to QA permits one
controlled handoff only. Agents must never repeat the cycle autonomously:

`user -> Build -> one QA handoff -> verdict -> stop`

The following autonomous loop is prohibited:

`Build -> QA -> Build -> QA -> ...`

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
