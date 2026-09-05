# FINN Authenticated Runtime Gate

Status: canonical

## Purpose

This gate validates the real authenticated FINN V2 path:

`gateway -> run creation -> dispatch -> worker -> terminal persistence -> polling/SSE`.

It is distinct from selector-only evaluation and must run against the release
SHA being considered for QA.

## Preconditions

1. `origin/main`, production checkout, public backend health, and frontend
   build information identify the same release SHA.
2. The approved fixture is bound by `FINN_QA_USER_ID` according to
   [FINN QA Fixture Contract](finn-qa-fixture-contract.md).
3. The token helper and runtime-gate scripts are present in the deployed tree.
4. The fixture snapshot confirms that its bot is non-live and no test requires
   a confirmation or execution.

Any failed precondition blocks the gate. It is an operational failure, not a
reason to select another user or weaken the test.

## Safe Server-Side Invocation

Run the issuer and gate in one server-side shell process. The token must remain
in process memory only. The following is intentionally schematic: operations
must supply the secret environment and must not copy a token into the command
or its output.

```bash
set -euo pipefail
set +x
# Source the server secret environment here.
# Read FINN_QA_USER_ID only from that environment.
# Mint with qa_issue_finn_token.py --user-id "$FINN_QA_USER_ID".
# Pass the captured token only to run_finn_v2_authenticated_smoke_gate.py.
# Unset the token before the shell exits.
```

Use `https://tradamind.com` for the transport path. The server-local process
may perform the required read-only persistence assertions using the existing
`run_finn_v2_authenticated_smoke_gate.py` wrapper.

## Required Evidence

For every submitted case, record only safe metadata:

- HTTP status and non-null run ID;
- initial/final operation, canonical target, and conversation reference;
- terminal status and typed terminal projection;
- polling/SSE equality;
- one dispatch and at most one attempt;
- latency and safe phase timings;
- write, execution, proposal, and bot-live counts.

Never include bearer tokens, credentials, user identifiers, email addresses,
or raw private fixture data in artifacts.

## Stop Rules

Stop immediately when token issuance, run creation, terminalization, transport
parity, safety, or fixture isolation fails. Do not retry an official QA run to
obtain a better result. A single documented infrastructure retry is allowed
only when repository governance explicitly permits it.
