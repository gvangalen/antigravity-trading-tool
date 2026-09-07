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
| `qa_profile` | `auth_preflight`, `targeted_regression`, `runtime_acceptance`, `full_release_acceptance`, `safety`, or `latency`. |
| `manifest_id` | Approved QA-owned manifest identifier. `auth_preflight` uses `none`. |
| `run_label` | Safe trace label; no user, fixture, or credential data. |

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
  `/home/ubuntu/ops/finn-qa-manifests`). Build never reads that material. The
  runner rejects a manifest that requests confirmation, execution, or fixture
  writes.
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

## Start A User-Authorized QA Run

After the user has authorized the active QA goal, a QA agent can start and
follow the protected runner without SSH:

```bash
./ops/qa/run_finn_production_qa.sh \
  <FULL_LIVE_SHA> auth_preflight none qa-preflight-<label>
```

For an approved read-only manifest, replace the profile and manifest ID. Read
the sanitized artifact from the resulting workflow run and issue one verdict
for exactly that approved scope.
