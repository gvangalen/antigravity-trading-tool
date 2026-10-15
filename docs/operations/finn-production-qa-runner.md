# FINN Production QA Runner

Status: canonical

## Purpose

`FINN Production QA` is the only supported executor for authenticated FINN
production QA. It runs from the protected GitHub Actions `production`
environment and, when needed, invokes the existing production-host token issuer
inside one non-logging server-side process. A QA chat never receives SSH keys,
database credentials, fixture identities, cookies, or bearer tokens.

Build implements and validates this runner but does not start an official QA
run. Only the user may authorize an official QA run; QA owns the active goal,
scope, dataset, matrix, and verdict.

## Inputs

The manual workflow `.github/workflows/finn-production-qa.yml` requires:

| Input | Meaning |
| --- | --- |
| `release_sha` | Full, already-live SHA. It must be an ancestor of `main`. |
| `qa_profile` | `auth_preflight`, `manifest_key`, `targeted_regression`, `runtime_acceptance`, `action_contract_acceptance`, `full_release_acceptance`, `safety`, `latency`, `score2_stale_paper`, or `auto_paper_trade_history`. |
| `manifest_id` | Approved QA-owned manifest identifier. `auth_preflight` uses `none`. |
| `run_label` | Safe trace label; no user, fixture, or credential data. |
| `manifest_bundle` | Optional encrypted QA-owned manifest. It is decrypted only on the protected host. |
| `allow_fixture_actions` | Explicit per-run permission for allowlisted QA-fixture proposals and confirmations; defaults to `false`. |
| `allow_safe_fixture_execution` | Explicit per-run permission for the non-financial fixture-execution allowlist or the separately named virtual EUR 50 `auto_paper_trade_history` profile; defaults to `false` and requires `allow_fixture_actions=true`. |

The profile defines only the execution class. The active QA goal remains the
authority for scope, acceptance criteria, and whether a sealed QA manifest is
allowed. The workflow never silently substitutes a sealed 32-case matrix.

`action_contract_acceptance` is the strict registry-wide profile. Before any
product request it requires exactly one independent case for every active
registry contract, all 16 safe write contracts, all nine declared natural
lineage dependencies, and the complete acceptance evidence schema. Write
cases capture owner-scoped database snapshots before confirmation, after
confirmation, after execution, and after idempotency replay.

## Security Boundary

- The runner uses only `FINN_QA_USER_ID` from the production secret environment.
  It never uses `FINN_BUILD_SMOKE_USER_ID`, an administrator, or a normal user.
- `qa_issue_finn_token.py` executes only on the protected host. Its JSON is
  captured in memory; the bearer token is never echoed, stored, exported, or
  uploaded.
- The workflow has read-only GitHub permissions, runs in the protected
  `production` environment, and uses a restricted SSH secret solely to invoke
  the runner. Configure `QA_SSH_HOST`, `QA_SSH_PRIVATE_KEY`, and the pinned
  host-key secret `QA_SSH_KNOWN_HOSTS`; the existing deploy host/key are a
  backward-compatible fallback, never a fallback for host verification.
- Every non-preflight manifest is resolved by ID from the protected,
  QA-owned server manifest root `/home/ubuntu/.secrets/finn-qa-manifests`.
  Build never reads that material. The earlier `/home/ubuntu/ops` default was
  not writable by the protected runner and stopped intake before any cases.
  QA can additionally stage an encrypted manifest bundle for one run; its
  plaintext exists only in the protected host directory with mode `0600`.
- `manifest_key` publishes only the server's manifest-encryption public key in
  a sanitized artifact. The private key remains in the server secret directory.
  The runner never accepts plaintext manifests through workflow inputs.
- Runtime cases remain read-only unless the active QA goal explicitly authorizes
  them and the protected workflow run sets the relevant per-run authorization
  input. Those values are exported only to the runner subprocess; they do not
  change production application configuration. Live trading and live-bot
  activation are never allowed by this runner.
- Reports contain only sanitized metadata: release identity, profile, case ID,
  run ID, operation/target metadata, lifecycle, timing, dispatch/attempt
  metadata, and safe safety counters. Headers, response contents, fixture
  identity, credentials, and private evidence are excluded.
- The workflow uploads the sanitized report plus a SHA-256 sidecar. Non-
  preflight reports also include the approved manifest SHA-256.

## Preflight

Every profile first verifies the exact requested SHA against the protected
checkout and release marker, public backend health, and frontend build info. It
then validates DNS/connect/TLS/client-timeout/server-response outcomes and uses
the in-memory token only for `/api/auth/me`. A `599` is always classified as
`dns`, `connect`, `tls`, `clienttimeout`, or `client`; SSH failures are
separately reported as `ssh` by the workflow artifact.

`auth_preflight` stops there. It is the only profile used to validate this
operational provision; it does not submit a FINN content case.

## QA-Owned Manifest Intake

QA first runs `manifest_key` and reads the public key from its sanitized
artifact. QA encrypts its locally held, goal-approved manifest without placing
the plaintext in the repository or an artifact:

```bash
python3 ops/qa/finn_qa_manifest_bundle.py encrypt \
  --public-key <PUBLIC_KEY_FROM_ARTIFACT> \
  --manifest <QA_OWNED_MANIFEST.json> > /tmp/finn-qa.bundle
```

The protected workflow receives only this encrypted bundle. It decrypts and
validates it on production, stores it under the QA-owned manifest root, and
reports only its SHA-256. Build never reads the plaintext or the sealed
holdout.

## Start An Independent QA Run

After the live candidate and agreed QA scope are documented, the existing QA
Agent can receive the assignment from Build and start or follow the protected
runner without SSH. Build cannot run this workflow or access its protected
material:

```bash
./ops/qa/run_finn_production_qa.sh \
  <FULL_LIVE_SHA> auth_preflight none qa-preflight-<label>
```

For an approved QA-owned manifest, replace the profile and manifest ID and add
the encrypted bundle path as the fifth argument. Read the sanitized artifact
from the resulting workflow run and issue one verdict for exactly that approved
scope.

## Fixture Action Boundary

Each manifest case has `fixture_action`, defaulting to `read_only`. The only
other accepted values are `proposal`, `confirmation`, and `safe_execution`.
They are executable only when the active QA goal authorizes them and the
protected workflow dispatch sets `allow_fixture_actions=true`;
`safe_execution` additionally requires
`allow_safe_fixture_execution=true`. The values are process-scoped runner
policy, not persistent production configuration.

Every non-read-only case must name an `expected_operation_id` in the existing
`SAFE_FIXTURE_EXECUTION_OPERATION_TYPES` execution-gate allowlist. The runner
therefore rejects `manual_order`, `portfolio_rebalance`, `activate_live_bot`,
and every other operation outside the existing safe fixture boundary before a
proposal route is called. Confirmation tokens remain process-local and are
never written to the report. An optional `idempotency_replay: true` is allowed
only for a `safe_execution` case and reuses the same idempotency key once.

## Runtime Matrix Semantics

`conversation_id` in a manifest is a QA-local conversation key, never a
production identifier. The first turn for a key omits `conversation_id`; the
gateway creates the conversation and the runner retains only the returned
identifier in memory for later turns with that same key. This makes parent and
child runs exercise persisted lineage and guided state without inventing IDs.

For every terminal turn the sanitized artifact retains contract ID and
revision, initial/final operation, target and lineage references, supplied and
missing inputs, typed terminal reason, proposal lifecycle and safe timings.
It never retains response content, evidence bodies, confirmation tokens, or
fixture identity. Proposal cases first read the proposal metadata and then use
the required confirmation idempotency key. A case mismatch is reported as QA
evidence while the runner exits normally so the complete matrix artifact is
uploaded; malformed runner configuration and pre-case infrastructure failures
still fail the workflow.

The report also separates case failures into `product`, `infrastructure`, and
`runner` totals. Transport failures cannot be counted as selector or action
contract failures.

## Stale Score 2.0 Paper Probe

`score2_stale_paper` is an explicit, one-shot protected QA profile. It requires
`manifest_id=none` and both fixture authorization inputs set to `true`; it
cannot run through a public endpoint or a scheduled job. The existing QA Agent
starts it only when its active scope authorizes this synthetic production test.
The runner first verifies the live SHA and the bound protected QA account.

The probe creates a separate, inactive, random-password synthetic owner marked with
the run namespace and no exchange keys. The regular bot dispatcher cannot
select this inactive owner. It writes only rows scoped to that temporary
owner: fresh DXY and RSI readings, plus a `change_24h` reading first proven
scoreable while fresh and then aged to 30 days,
one Smart-DCA setup and strategy, and one manual Paper bot with virtual cash.
It never inserts global market history or changes a normal user's data. The
canonical Score 2.0 builder and bot assessment are then called for exactly
that owner and bot. The assessment uses the production code in the protected
host process; the local Celery probe remains the separate worker-path proof.

The profile passes only if Macro and Technical score, Market stays unknown,
the persisted decision is Hold for EUR 0, the score-driven amount is
unavailable, there are no bot orders or ledger entries, and virtual cash is
unchanged. It checks that the old source still exists after assessment;
if a refresh races the fixture, the run fails instead of claiming a pass. The
Paper bot is deactivated before the temporary owner and its rows are removed
after a passing check. A failed check quarantines the bot and retains the
evidence for a separately authorized fixture reset. If cleanup fails, the run
fails and the bot is deactivated. The artifact emits
only these safe outcomes, with no owner or bot IDs, tokens, raw readings, or
database rows.

Example for the existing QA Agent after a user-approved scope and live Build
candidate:

```bash
FINN_QA_ALLOW_FIXTURE_ACTIONS=true FINN_QA_ALLOW_FIXTURE_EXECUTION=true \
  ./ops/qa/run_finn_production_qa.sh \
  <FULL_LIVE_SHA> score2_stale_paper none qa-score2-stale-paper
```

For a proposal/action case, `expected_missing_inputs` may list the canonical
required fields that are intentionally absent on that turn. A matching typed
`missing_inputs` response is a valid guided-flow outcome, not
`proposal_missing`; a later case using the same conversation key can supply
the missing values and require the resulting proposal lifecycle.

## Automatic Paper Trade History Probe

`auto_paper_trade_history` is a separate one-shot protected QA profile. It
requires `manifest_id=none`, an empty manifest bundle, and both fixture
authorization inputs set to `true`. Only independent QA starts it for an
explicit user-approved Paper-order goal after the exact live SHA is recorded
as a complete candidate in `FINN_RELEASE_STATUS.md`. It does not widen the
general FINN safe-execution operation allowlist.

The probe checks the bound QA fixture, then creates one inactive, random-
password synthetic owner with a run namespace and no exchange keys. It seeds
one auto Paper bot with EUR 100 virtual funding, a plan-revision-bound buy
decision, and one EUR 50 proposed order. The production automatic Paper
executor must fill exactly that order. The probe then checks the owner-scoped
order, execution, ledger, virtual cash and the same account trade-history
service used by `/api/bot/trades/all`: one `paper` / `auto` / `filled` entry
for EUR 50 and EUR 50 remaining cash. This proves the automatic Paper executor
and history projection, not the market scoring/decision scheduler or browser
rendering. There are no broker credentials, Live calls, shared market writes,
or ordinary user writes.

The inactive owner is outside the regular bot dispatcher. On success, the
probe durably deactivates the bot before deleting only rows under the
run-namespace-checked synthetic owner. On failure it deactivates the bot and
keeps the rows for a separately authorized fixture reset. Cleanup failure
fails the run and leaves the owner inactive and bot deactivated. The sanitized
artifact contains only fixed outcome fields, not owner/bot/order IDs or raw
database rows.

QA invocation after the candidate is live:

```bash
FINN_QA_ALLOW_FIXTURE_ACTIONS=true FINN_QA_ALLOW_FIXTURE_EXECUTION=true \
  ./ops/qa/run_finn_production_qa.sh \
  <FULL_LIVE_SHA> auto_paper_trade_history none qa-auto-paper-history
```
