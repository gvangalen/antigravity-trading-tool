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
| `qa_profile` | `auth_preflight`, `manifest_key`, `targeted_regression`, `runtime_acceptance`, `full_release_acceptance`, `safety`, or `latency`. |
| `manifest_id` | Approved QA-owned manifest identifier. `auth_preflight` uses `none`. |
| `run_label` | Safe trace label; no user, fixture, or credential data. |
| `manifest_bundle` | Optional encrypted QA-owned manifest. It is decrypted only on the protected host. |
| `allow_fixture_actions` | Explicit per-run permission for allowlisted QA-fixture proposals and confirmations; defaults to `false`. |
| `allow_safe_fixture_execution` | Explicit per-run permission for the existing non-financial fixture-execution allowlist; defaults to `false` and requires `allow_fixture_actions=true`. |

The profile defines only the execution class. The active QA goal remains the
authority for scope, acceptance criteria, and whether a sealed QA manifest is
allowed. The workflow never silently substitutes a sealed 32-case matrix.

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
  QA-owned server manifest root (`FINN_QA_MANIFEST_ROOT`, defaulting to
  `/home/ubuntu/ops/finn-qa-manifests`). Build never reads that material.
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

## Start A User-Authorized QA Run

After the user has authorized the active QA goal, a QA agent can start and
follow the protected runner without SSH:

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
