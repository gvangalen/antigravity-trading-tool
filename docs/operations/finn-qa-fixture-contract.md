# FINN QA Fixture Contract

Status: canonical

## Purpose

This contract defines the approved identities used for authenticated FINN
release validation. It prevents an agent from selecting an account by email
pattern, role, recency, or any other heuristic.

## Canonical Identity

The production secret environment must define two distinct numeric identifiers:

- `FINN_BUILD_SMOKE_USER_ID` for the Build-only authenticated smoke;
- `FINN_QA_USER_ID` for independent QA cases defined by the active QA goal.

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

### Inactive synthetic score probe owner

The user-authorized `score2_stale_paper` protected QA profile may create one
temporary **inactive** synthetic owner per run for data isolation. It is not
an authenticated Build or QA fixture and receives no token or exchange key.
The runner first verifies the bound `FINN_QA_USER_ID` and its protected marker;
the synthetic owner is identified only by a random run namespace and its own
`qa_fixture` marker. No ordinary user or shared market row may be changed.
The normal bot dispatcher selects only active users, so it cannot schedule
this inactive owner. The profile calls the canonical scorer and assesses only
its manual Paper bot; it never calls an exchange or activates Live mode.

Successful validation may remove only this run's synthetic rows through the
exact owner-and-namespace-checked cleanup in the protected probe. On failure,
the bot is disabled and data is retained for diagnosis. Removing a failed
probe requires a separately authorized protected fixture reset, never an
automatic retry that erases failing evidence. This exception does not permit
a second login fixture or change either server binding.

### Inactive synthetic automatic Paper history owner

The user-authorized `auto_paper_trade_history` protected profile has the same
bound-QA-account and namespace requirements. It may create one separate,
inactive synthetic owner with no exchange keys, one auto Paper bot, EUR 100
virtual funding and one EUR 50 Paper buy. Its only execution call is the
canonical automatic Paper executor with `is_live=False`; it checks the
owner-scoped order, ledger and account trade-history projection. It never
changes shared market rows or ordinary user data, activates Live mode, calls
an exchange, or grants the synthetic owner a login token. The general FINN
safe-execution allowlist remains unchanged.

The protected workflow requires both per-run fixture authorization flags and
an active QA goal naming this exact test. The probe deactivates the bot and
retains failed evidence. Successful cleanup requires an exact owner marker
and run namespace and commits bot deactivation before deleting fixture rows.
See [the runner contract](finn-production-qa-runner.md) for its sanitized
evidence and coverage limits.

## Token Handling

The existing
`backend/trading-tool-backend/backend/scripts/qa_issue_finn_token.py` helper
is the only approved bearer-token issuer for these gates. Invoke it on the
production host with the user ID appropriate to the caller inside one
non-logging shell process.

- Disable shell tracing before sourcing secrets or issuing a token.
- Capture the helper output internally and pass only `access_token` to the
  next gate process through an environment variable.
- Never print the helper JSON, token, Authorization header, email, or user ID.
- Do not write the token to files, command history, repository artifacts, or a
  local shell.
- Unset the token immediately after the gate terminates.

If either required binding is absent, malformed, inactive, or does not identify
its approved fixture, the corresponding gate is blocked. Do not select a
fallback user, mint a local JWT, or use a browser cookie. Missing fixture
bindings may be restored only by Operations under explicit user authorization
through the protected `FINN QA Fixture Operations` workflow. Its provision mode
creates distinct, designated, marked, non-admin Build and QA owners with
unknown generated passwords. It checks that neither has exchange keys and
writes bindings only to the server secret environment. It never prints or
exports owner IDs. Re-running may use only those exact marked owners; different
existing accounts are never selected. Run `auth_preflight` after provisioning
before any product cases.

## Fixture Safety

Before and after a runtime or QA run, take read-only snapshots of the approved
fixture records needed to prove no unexpected execution, trade, live-bot
activation, or business write occurred. The separately authorized automatic
Paper history probe expects exactly one owner-scoped virtual Paper execution;
every other execution remains unexpected. A proposal-only test is not an
execution test and must not confirm a proposal.

The fixture may be reset only through an explicitly approved fixture-reset
procedure. Never delete or alter records to hide a failed validation.

## Ownership

Operations owns the server-side fixture bindings. Build may use only
`FINN_BUILD_SMOKE_USER_ID` for generic non-sealed smoke cases; QA may use only
`FINN_QA_USER_ID` for goal-defined independent QA. Neither binding grants
Build access to the QA fixture or QA-exclusive sealed holdout. QA uses the
protected [FINN Production QA Runner](finn-production-qa-runner.md), so the
fixture identity and bearer token never leave the server-side process.
