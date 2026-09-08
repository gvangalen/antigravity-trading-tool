# FINN Release Process

## Purpose

This is the canonical process for building, releasing, and independently
testing FINN. It preserves the repository's existing Build, QA, Security, and
Architecture roles; it does not create additional agent roles.

## Roles

### Build

Build implements one complete repair batch, reproduces known defects locally,
adds regressions, validates the relevant chain, creates one release candidate,
runs CI, deploys, and verifies the deployed SHA and public health surfaces.
Before deployment, Build must run the complete local worker-driven action
matrix for affected action contracts, real-provider development/regression,
and applicable backend/frontend suites. Build updates
`FINN_RELEASE_STATUS.md` only with measured evidence. Build does not start,
instruct, or contact QA, access the QA fixture, or access the QA-exclusive
sealed holdout. The Build smoke fixture is optional diagnostic tooling, not a
release gate.

### QA

QA owns independent test execution, QA test material, and the protected
`FINN_QA_USER_ID` authenticated runtime route. Its active QA goal defines the
concrete scope, dataset, environment, matrix, and acceptance criteria.
Production QA is read-only and tests only the explicit live SHA in its active
QA goal. QA preflight verifies that SHA against the production checkout,
release marker, public backend health, and frontend build-info. A
committed status document cannot be the identity authority for its own
deployment SHA because changing it creates a new SHA. The sealed holdout is QA-exclusive and QA uses it
unchanged only when its active QA goal explicitly requires it. QA completes the
entire agreed matrix even after individual content failures and records a
single evidence-backed verdict for that scope. QA does not modify product
state, deploy, or direct another agent.

### Security and Architecture

These roles remain read-only unless the user explicitly grants implementation
authority. They do not take over Build or QA responsibility.

## One Active Release

Only one FINN candidate may be active. Its branch, candidate SHA, production
SHA, phase, evidence, and QA outcome live only in `FINN_RELEASE_STATUS.md`.
Do not replace a candidate while official QA is running, and do not add new
technical changes to the candidate under QA.

## Build and Release

Build handles all defects in the active goal as one coherent batch:

1. reproduce each defect and identify its root cause;
2. repair the implementation and add a regression test;
3. re-run the focused test;
4. run all applicable suites after the batch is complete;
5. run the complete local worker-driven action matrix for every affected
   action contract, real-provider development/regression, and the applicable
   backend/frontend suites;
6. create and push one candidate;
7. require successful CI, deploy the exact candidate, and verify that Auto
   Deploy succeeded, backend health returns `200`, frontend build-info is
   reachable, and backend and frontend report the deployed SHA.

Known red regressions, lower thresholds, weaker assertions, removed cases, or
new skips never constitute a green Build gate. Full runtime claims require
end-to-end evidence; provider claims use the real provider. The sealed holdout
is QA-exclusive and Build must not read, copy, score, tune against, or submit
it through any local or live route.

`FINN_BUILD_SMOKE_USER_ID` remains available only for voluntary, generic,
non-sealed production diagnosis. It is not a deployment or independent-QA
precondition and never grants access to the QA fixture or sealed holdout.

## Independent Production QA

Only the user determines or authorizes an independent QA assignment. For
production QA, the user starts the existing QA agent after the status file
documents `READY_FOR_INDEPENDENT_QA` with Build's local and deployment
evidence. QA reads the role instructions, this process, the status file, and
its explicit QA goal; then uses the protected `FINN_QA_USER_ID` route to run
the goal's authenticated preflight, runtime/dispatch checks, controlled
fixture actions where authorized, polling/SSE and safety checks, and the
complete matrix defined by that goal. Individual case failures are recorded
and do not stop later cases. A sealed 32-case matrix is mandatory only when
the active QA goal explicitly requires it. Timeouts remain failures under the
QA contract.

QA publishes `ACCEPTED` or `NOT_ACCEPTED` once, with artifacts and hashes. The
verdict does not start Build, deployment, or another QA run automatically.

## Evidence Rules

- Do not call anything executed, green, live, or accepted without verifiable
  evidence in `FINN_RELEASE_STATUS.md`.
- Intent, progress, technical validation, release status, and independent QA
  verdict are different states.
- Report missing observability as missing; never infer it.
- Mobile follow-ups may refer only to this process, the current status, their
  role, and the active goal instead of restating the release contract.
