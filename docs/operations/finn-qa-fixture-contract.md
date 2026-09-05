# FINN QA Fixture Contract

Status: canonical

## Purpose

This contract defines the approved identities used for authenticated FINN
release validation. It prevents an agent from selecting an account by email
pattern, role, recency, or any other heuristic.

## Canonical Identity

The production secret environment must define two distinct numeric identifiers:

- `FINN_BUILD_SMOKE_USER_ID` for the Build-only authenticated smoke;
- `FINN_QA_USER_ID` for independent QA and its QA-exclusive sealed holdout.

Both values are server-only and must not be committed, printed, copied to a
workstation, or included in test artifacts. The bindings must never resolve to
the same account.

The designated account must:

- be a non-administrative, non-production-user QA fixture;
- have only the normal FINN permissions required by the runtime gate;
- be isolated from ordinary user data;
- have a documented safe fixture workspace and bot state;
- remain non-live by default.

There is exactly one active fixture of each kind per production environment.
Changing either binding is an operational change: update the server-side
secret, verify the account, and record the change in the deployment handoff.
Do not infer a replacement from the users table.

## Token Handling

The existing `backend/scripts/qa_issue_finn_token.py` helper is the only
approved bearer-token issuer for these gates. Invoke it on the production host
with the user ID appropriate to the caller inside one non-logging shell
process.

- Disable shell tracing before sourcing secrets or issuing a token.
- Capture the helper output internally and pass only `access_token` to the
  next gate process through an environment variable.
- Never print the helper JSON, token, Authorization header, email, or user ID.
- Do not write the token to files, command history, repository artifacts, or a
  local shell.
- Unset the token immediately after the gate terminates.

If either required binding is absent, malformed, inactive, or does not identify
its approved fixture, the corresponding gate is blocked. Do not select a
fallback user, mint a local JWT, create an account, or use a browser cookie.

## Fixture Safety

Before and after a runtime or QA run, take read-only snapshots of the approved
fixture records needed to prove no execution, trade, live-bot activation, or
unexpected business write occurred. A proposal-only test is not an execution
test and must not confirm a proposal.

The fixture may be reset only through an explicitly approved fixture-reset
procedure. Never delete or alter records to hide a failed validation.

## Ownership

Operations owns the server-side fixture bindings. Build may use only
`FINN_BUILD_SMOKE_USER_ID` for generic non-sealed smoke cases; QA may use only
`FINN_QA_USER_ID` for independent QA. Neither binding grants Build access to
the QA fixture or QA-exclusive sealed holdout. Both use the bounded procedure
in `finn-authenticated-runtime-gate.md`.
