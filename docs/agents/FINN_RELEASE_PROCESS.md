# FINN Release Process

## Purpose

This is the canonical process for building, releasing, and independently
testing FINN. It preserves the repository's existing Build, QA, Security, and
Architecture roles; it does not create additional agent roles.

## Roles

### Build

Build implements one complete repair batch, reproduces known defects locally,
adds regressions, validates the relevant chain, creates one release candidate,
runs CI, deploys, and performs the bounded authenticated live smoke. Build
updates `FINN_RELEASE_STATUS.md` only with measured evidence. Build does not
start, instruct, or contact QA.

### QA

QA is read-only and independently tests only the live SHA recorded in
`FINN_RELEASE_STATUS.md`. QA uses the sealed holdout unchanged, completes the
entire prescribed matrix even after individual content failures, and records a
single evidence-backed verdict. QA does not modify product state, deploy, or
direct another agent.

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
5. create and push one candidate;
6. require successful CI, deploy the exact candidate, and verify backend,
   frontend, checkout, and release markers;
7. run the bounded authenticated live smoke and record its evidence.

Known red regressions, lower thresholds, weaker assertions, removed cases, or
new skips never constitute a green Build gate. Full runtime claims require
end-to-end evidence; provider claims use the real provider. Build never uses
the sealed holdout for tuning or validation.

The live smoke is Build validation, not independent QA. It uses no sealed QA
case and covers the current batch's critical paths plus run creation,
read-only capability, EVALUATE, a conversation follow-up, terminalization,
polling/SSE parity, dispatch cardinality, safety, and latency.

## Independent Production QA

Only the user starts the existing QA agent after the status file documents
`READY_FOR_INDEPENDENT_QA` with evidence. QA reads the role instructions, this
process, the status file, and its explicit QA goal; then tests exactly the
recorded live SHA and completes its whole matrix. Individual case failures are
recorded and do not stop later cases. Timeouts remain failures under the QA
contract.

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
