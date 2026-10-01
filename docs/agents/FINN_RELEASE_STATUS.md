# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; required local Build and deployment gates passed. |
| Active goal | Repair the user-reported coach failures on live SHA `94913335abaed9f82c9824bc268dc783f1cc0107`: a combined numbered-setup/evidence follow-up dropped its evidence, a named BTC setup could receive levels from another BTC strategy or generic FOMO coaching, and a BTC-to-AAPL rule question could lose its asset boundary when FOMO was mentioned. |
| Candidate branch | `codex/finn-coach-identity-boundary` ([PR #29](https://github.com/gvangalen/antigravity-trading-tool/pull/29), merged). |
| Candidate code SHA | `c0cb0d7ac8e7179103734b0d215f120ecd04e7ad`. |
| Production code SHA | `ad071b66c638e20a655495e68281f10bc61ccd65`, verified on public backend health and frontend build-info at 11:35 UTC on 2026-10-01. This status-only follow-up creates another deploy SHA; verify that runtime identity separately. |
| Release owner | Build |
| Last updated | `2026-10-01` |

The user's targeted authenticated live recheck is **not accepted** for its
coach scope. Build did not access the protected QA fixture or sealed holdout,
and the new candidate needs independent authenticated QA after deployment.

## Investigation and Repair

- The combined “second from your list + what do you know for certain” turn
  resolved the verified inventory position but only set the evidence flag when
  the previous turn had already selected one item. The route now sets that
  flag from either verified path and rereads the selected owner-scoped ID.
- The Responses read catalog cannot carry model-supplied setup IDs. The front
  door previously bound a named setup only for `get_active_plan_and_strategy`,
  leaving evaluation reads with an asset such as `BTC` that may match several
  setups. It now resolves a setup named in the user message against the
  owner's records and supplies that ID to evaluation reads as well.
- An explicit strategy ID or name can no longer override a different
  selected setup in the graph resolver. The answer verifier now checks stated
  entry, stop and target prices against the linked strategy returned in that
  turn. If model coaching is rejected after a verified named setup and linked
  strategy read, a source-bound coach answer preserves that setup's saved
  levels instead of discarding the facts into generic FOMO advice.
- A question applying a rule named for one asset to another now takes the
  typed cross-asset route even when FOMO appears elsewhere in the message.

The live report did not include a run ID or server trace. The precise path
that produced its `80.000/76.000` claim is therefore unproven. A synthetic
worker-driven repro did prove the separate verifier issue: FINN read the
correct `BTC Full Base` strategy and drafted `76.000/72.000`, but a verifier
rejection replaced it with generic FOMO advice. A subsequent run on the
repair kept the correct levels and the BTC-to-AAPL boundary. This is local
Build evidence, not authenticated live acceptance.

## Local Build Evidence

The disposable parity stack uses isolated PostgreSQL, Redis, API and Celery
with synthetic users. FINN chat uses `gpt-6-luna` with reasoning `none`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Targeted API/Celery coach sequence | `4/4` completed without proposals: list, combined ordinal/evidence follow-up, named `BTC Full Base` FOMO/levels (`76.000/72.000`), and BTC-to-AAPL/FOMO. | `.local-finn-parity-artifacts/coach-identity-repro.json`, SHA-256 `48be34e4528ef2bc9289b505d36baf6d02df665bd9797650ee4f6b5cef72bbe8`. |
| Full safe action-contract matrix on final code | `16/16`; zero broker orders, live bots, live-trading calls, or production connections. | `.local-finn-parity-artifacts/coach-identity-action-matrix-release.json`, SHA-256 `fbebfb651efb4bff1fbac67a2aac89edcde0c91515fcab532009e80540d89c63`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-identity-provider-development.json`, SHA-256 `7349647428ed085dbb3cd8530bd5b7ad685f29b0e1e46db0cfc62085cb3e6648`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/coach-identity-provider-regression.json`, SHA-256 `95cd924916776d439bf37d7fa9280a4773f34c9b679a7fd28bfa573167741446`. |
| Backend canonical suite | `2922 passed, 3 skipped` on final code. | `pytest -q --disable-warnings`. |
| Frontend canonical checks | Passed; no frontend source changes. | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, production `build`. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: PR run `36855835737`, all five jobs green. |
| Main CI | `PASS`: main run `36856041731`, all five jobs green. |
| Auto Deploy | `PASS`: run `36856206900` deployed merge SHA `ad071b66c638e20a655495e68281f10bc61ccd65`. |
| Backend health and frontend build-info | `PASS`: both HTTP 200 and both reported the merge SHA at 11:35 UTC on 2026-10-01. |
| Independent authenticated live QA | Pending; QA owns the protected fixture and verdict. |

Build's local and deployment checks establish technical readiness only.
Authenticated production acceptance remains independent QA's responsibility.
