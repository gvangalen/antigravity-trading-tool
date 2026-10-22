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
`FINN_RELEASE_STATUS.md` only with measured evidence. After documenting a
complete live candidate, Build assigns the agreed independent test scope
to the existing QA Agent and follows up in that same task. The user's standing
authorization covers this routine handoff after each verified FINN deployment;
Build does not ask again for permission for each SHA. Build does not run
the official QA workflow, access the QA fixture, or access the QA-exclusive
sealed holdout. The Build smoke fixture is optional diagnostic tooling, not a
release gate.

Before that QA handoff, Build waits for the **last** main CI and Auto Deploy
triggered by the candidate or its status update to finish. The GitHub main
commit, successful deploy run, public backend SHA, and public frontend SHA
must all identify the same final revision, with no newer deployment pending.
An earlier skipped Auto Deploy run does not satisfy this check when a later
main CI completion can trigger another deploy. The QA Agent then tests that
final public revision; Build does not change the active candidate during QA.

### QA

QA owns independent test execution, QA test material, and the protected
`FINN_QA_USER_ID` authenticated runtime route. Its active QA goal defines the
concrete scope, dataset, environment, matrix, and acceptance criteria.
Production QA is read-only by default and tests only the explicit live SHA in
its active QA goal. Explicitly authorized protected fixture operations follow
the narrow runner and fixture contract; they do not grant access to normal
users or Live trading. QA preflight verifies that SHA against the production checkout,
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

The user sets the product goal and may direct the QA scope. The user has
authorized Build to initiate the agreed independent QA after each verified
FINN deployment without a new permission request for that SHA. Once the status
file documents a complete live candidate with Build's local and deployment
evidence, Build sends the assignment to the existing QA Agent and follows up
there. Reuse that agent and task across test steps and repair cycles;
do not create a new QA agent or task for each step. QA decides its own test
execution and verdict independently. Build cannot invoke the protected QA
runner or inspect QA-only storage, fixtures, manifests, or the complete sealed
holdout. QA gives Build the relevant failed-case evidence directly for repair.
The standing authorization does not expand the agreed QA scope or permit Live
orders, changes to ordinary users, or new kinds of protected fixture writes.
Those still require explicit user authorization. QA still checks the exact
deployed SHA and the operation permissions required by its active goal and
runner contract before every official run.
QA reads the role instructions, this process, the status file, and its
explicit QA goal; then uses the protected `FINN_QA_USER_ID` route to run
the goal's authenticated preflight, runtime/dispatch checks, controlled
fixture actions where authorized, polling/SSE and safety checks, and the
complete matrix defined by that goal. Individual case failures are recorded
and do not stop later cases. A sealed 32-case matrix is mandatory only when
the active QA goal explicitly requires it. Timeouts remain failures under the
QA contract.

QA publishes `ACCEPTED` or `NOT_ACCEPTED` once, with artifacts and hashes. The
verdict does not start Build, deployment, or another QA run automatically.

For `NOT_ACCEPTED`, QA gives Build a concrete repair handoff in the existing
QA task without asking the user for another disclosure permission. Include
each failing case's exact user question, necessary preceding turns, expected
behavior, observed answer or proposal fields, relevant tool selection and
state, run ID, severity, and sanitized error code, trace or response. Include
an apparently passing case when independent review finds a safety failure that
the runner missed. QA may share further case-specific diagnostic evidence
directly with Build as needed to make the defect reproducible, without a new
permission question. QA does not transfer credentials, cookies, personal
fixture identifiers, the protected manifest, or the complete sealed dataset.
Build uses this handoff for local repairs and does not read QA-only storage.
QA keeps the verdict and retest independent.

## Evidence Rules

- Do not call anything executed, green, live, or accepted without verifiable
  evidence in `FINN_RELEASE_STATUS.md`.
- Intent, progress, technical validation, release status, and independent QA
  verdict are different states.
- Report missing observability as missing; never infer it.
- Mobile follow-ups may refer only to this process, the current status, their
  role, and the active goal instead of restating the release contract.
