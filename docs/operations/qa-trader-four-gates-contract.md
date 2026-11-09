# Protected QA contract: four trader gates

Status: QA-owned partial collectors, not four-gate acceptance. The trusted-ref
and deploy-event guards landed on `main` in PR #892. The pair-score and
Paper-exit profiles have produced partial production evidence; the new
account-answer examiner and browser renderer on this branch are not live QA
evidence. Security and Architecture review remains required before merge.
Never dispatch the protected workflow from this branch.

## Shared boundary

- Bind `FINN_QA_USER_ID` only inside the protected server process. Verify its
  marker, role, active state and absence of exchange keys before any fixture
  write. Never export the ID, token, prompt response, names or row contents.
- Use one random workflow namespace. Child owners are inactive, have random
  passwords, no login session and no exchange keys. Writes may touch only
  rows whose owner and namespace are both verified. No shared market source,
  provider quota, ordinary user, Live bot, broker route or release marker may
  be modified.
- Freeze expected source facts before invoking product code. A response cannot
  define its own expected operation, fact, score or source timestamp.
- On success, clean up only this namespace and verify zero retained rows. On
  any failed postcondition, disable the bot and quarantine the owner for
  bounded protected diagnosis; never delete unrelated rows.
- A sanitized artifact may publish only gate name, PASS/FAIL/BLOCKED, fixed
  invariant subcodes, counts, bounded error categories and workflow SHA. It
  must not publish fixture identities, values, text answers or raw SQL errors.
- If a required source or fixture contract is absent, report `BLOCKED` or
  `UNTESTED`, never `PASS`. Every collector has a bounded deadline and a
  `finally` cleanup/quarantine path. `live_trading_calls`, `broker_orders` and
  `live_bot_activation_calls` must each equal zero.

## Gate 1: FINN account state

Fixture: one owner-scoped plan/setup, linked strategy, inactive Paper bot,
Paper portfolio with a position, and two persisted bot decisions with distinct
times. Their source IDs and values stay inside the process. Obtain two FINN
read-only responses in one conversation and a third in a fresh conversation.
Before each turn, independently read the authoritative owner-scoped rows.
Require that FINN's answer names the plan, bot state, position and latest
decision correctly, or says exactly which source is absent. Check tool/evidence
owner and source ID, no proposal, no confirmation and no write. A response
whose factual claims cannot be machine-checked is `UNTESTED`, not `PASS`.

**Collector blocker:** current sanitized V2 envelope does not expose typed
answer claims for all four sources. Merely checking for response words cannot
prove factual consistency. An independently verifiable, owner-scoped answer
projection or protected local answer examiner is required; it must not export
the original response. This is not permission to make product changes in QA.

The proposed `trader_account_state_readback` profile creates an isolated
inactive Paper child owner, freezes its persisted plan, bot, position and
latest-decision facts before each turn, checks typed source evidence, and
uses a separate in-memory examiner twice per answer. It requires seven
separate factual claims across two fresh conversations and one follow-up.
The artifact contains only fixed check codes and counts. This is not a Gate 1
PASS until the protected profile runs on the deployed revision and its
postconditions, cleanup and model judgment are independently reviewed.

## Gate 2: one instant across four surfaces

Fixture: one dated exact-market price measurement and associated report, Analysis
quote, Paper bot evidence and FINN market read. The collector records the same source ID and
UTC instant internally, then reads each surface through its normal owner-scoped
route. Normalize explicit UTC and Amsterdam displays to the same instant;
verify visible zone labels and the short stale-indicator date over an offset
midnight boundary. A frontend check must execute the deployed formatter in at
least Amsterdam, New York and Tokyo browser zones; source-code inspection alone
is not live UI acceptance. Do not replace the source timestamp with a synthetic
string after the product read.

The QA-only `trader_source_time_parity` profile reuses an isolated automatic
Paper-exit child fixture. It freezes the dated exact-market quote before
execution, runs the normal report generator and writer without push/feed,
reads the saved report and Analysis through owner-scoped GETs, reads FINN's
market tool evidence, and checks Paper decision provenance. Its protected
browser renders the deployed Analysis and report pages in Amsterdam, New York
and Tokyo zones and returns only fixed booleans. This is not live acceptance
until the profile passes on the exact deployed revision.

**Source-identity contract:** exact-market quote projections carry an immutable
`market_data.id`, exact `market_id`, and UTC `source_observed_at` as a typed
source reference. FINN's `market_quote_source_ref` identifies only its
separately selected market quote; it does not identify an indicator reading or
prove the provenance of a calculated score. The report must retain the same
reference it snapshotted rather than substituting its generation time. New
market rows can arrive between reads, so QA must freeze or independently record
the expected row for each surface read. QA compares references internally and
publishes only equality booleans. Browser formatting and transport readback
remain required before Gate 2 can pass.

## Gate 3: two exact BTC markets through outage and recovery

Fixture: one owner with distinct exact market IDs for BTC/EUR and BTC/USDT,
separate saved indicator configuration and intentionally distinct initial
scores. Use only owner-specific indicator readings and daily score rows. Do
not change shared candles, pair quotes, FX or provider state. Capture initial,
outage and recovery snapshots. In the outage phase, make only the BTC/EUR
fixture reading stale or unavailable, and require a null BTC/EUR score plus
an independently proven fixture stale cause; report the product's actual
source status separately. BTC/USDT must retain its own score. On recovery,
restore a genuinely dated BTC/EUR reading, trigger the normal score rebuild,
and require its owner- and market-scoped result without changing BTC/USDT.
Check Analysis and FINN projections against the same canonical score rows.
The local pure invariant is `check_pair_score_isolation`; a collector must
supply independent database facts, not product-response-derived expectations.

`trader_pair_score_continuity` now uses a protected inactive child owner, the
actual dated market quote for each pair, owner-only indicator configurations,
the normal score builder, persisted `daily_scores` and the canonical
`SetupMarketMatchService` assessment. It reads both pairs before, during and
after an owner-only BTC/EUR source outage. The QA-only collector also reads
Analysis through the owner-scoped exact-market GET and FINN through read-only
chat/tool evidence in all three phases, then renders the stale source date in
three browser zones. It requires a fresh quote for
both pairs; otherwise the collector must fail without inventing a score.
When the builder correctly persists a NULL market score, the match service may
report `missing_score` rather than `stale_source`; the collector only accepts
that state when the pair remains isolated and a separate fixture check proves
the dated, owner-scoped stale reading. The collector verifies the actual
transport projections and rendered date; it does not assert that the UI or
FINN used the literal status string `stale_source`. No production PASS exists
until the extended collector runs on the deployed revision.

## Prior Paper-exit runner diagnosis

`trader_paper_exit_fixture_audit` is a read-only protected profile. With both
fixture-action flags false and `run_label=audit-<workflow-id>-<attempt>-<sha8>`,
it searches only the child namespace of that earlier workflow and publishes
fixed booleans for retained Paper rows and active/Live safety. It never emits
the namespace, owner, bot, values, SQL or error text. `NO_RETAINED_FIXTURE`
requires the prior sanitized report to identify the Paper-exit profile and
source SHA and prove the protected profile was attempted but failed or remained
incomplete; otherwise the audit stops before querying fixture rows.
`NO_RETAINED_FIXTURE`
does not prove cleanup: the earlier run may have failed before seeding, so the
audit outcome stays `incomplete` even when it finds no retained child. An
inactive retained fixture stays quarantined for bounded diagnosis; the audit
never deletes it and also reports an incomplete diagnostic outcome, not a
product PASS. Current inactivity does not prove a historical cleanup action.
The Paper-exit collector now translates unexpected errors
to fixed preflight/seed/open/baseline/engine/evidence stage codes before the
runner sanitizes them. An old `runner_internal` result cannot retrospectively
be assigned one of those stages without additional evidence.
After the read-only audit of run 42502525173 found a retained, inactive child
but no persisted Paper opening, the opening transaction gained fixed
lookup/update/insert/commit substage codes. They do not execute extra SQL or
publish error text. The earlier run remains `INCOMPLETE`; this diagnostic
change is for at most one separately authorized Paper-only hertest.

The one allowed hertest on live SHA `43b989b60ab08b55918deaefbccd4bd49e9a8a95`
ended before a Paper opening with fixed code
`paper_exit_open_strategy_update_failed`. The failed child remained inactive
and non-Live with no persisted Paper exit. `trader_strategy_schema_audit` is
a separate read-only protected diagnostic with no manifest or fixture-action
flags. It reads only metadata for `strategies.targets`, `market_id`, `data`,
`setup_type`, `entry`, and `stop_loss`, plus allowlisted constraint names and
bounded presence counts for other constraints and user triggers. It emits no
user rows, values, raw SQL errors, trigger definitions, or unknown names. A
schema match alone does not prove the failed UPDATE's root cause. The probe is
transferred with the QA control-plane runner and checksum-checked, so its own
presence does not depend on the product checkout. Its database helper still
comes from that checkout. After a QA-only main deployment, the audit
must target the then-current live SHA. It observes the current schema, not a
historical snapshot; any inference about the earlier failed UPDATE remains
conditional on no intervening schema change.

## Gate 4: automatic Paper exit and reproducible cashflow

Fixture: one inactive, uncredentialed Paper bot with a real open Paper position
and saved stop/target. Choose levels around a *read-only, dated* exact-pair
quote so the normal auto-exit engine triggers one sell. Never alter the shared
quote to force a trigger. Require one `paper_exit` decision, one filled Paper
order, one execution, one ledger sell leg and no second fill on replay. Compare
stored execution source price, currency, FX factor and both source times with
the order/ledger EUR unit price, filled quantity, EUR proceeds, portfolio
quantity and cash before/after. Read the owner-scoped bot-history projection
and rendered `PaperExitEvidence` fields; absence of a rendered field is FAIL,
not proof from the database alone. `check_paper_exit` returns only fixed
subcodes. It does not create a position or run the exit engine by itself.

The existing `portfolio_paper_fx` profile is a **buy** probe and the existing
`closed_paper_trade_review_chat` profile closes a position through a direct
Paper sell. Neither is an automatic-exit acceptance test. Historical PASSes
must not be imported as a PASS for this gate.

`trader_paper_exit_reconciliation` now seeds an owner-only Paper opening lot
against the existing dated BTC/USDT quote and FX, invokes the normal automatic
exit engine twice, and reconciles the persisted decision/order/execution,
ledger, portfolio and owner-scoped `BotService.get_bot_history` projection. It
also renders the deployed `PaperExitEvidence` component in a protected browser
and verifies decision quote, execution quote, FX, quantity and EUR values. Decision
source and execution source are checked separately: EUR fill arithmetic uses
the recorded execution quote and FX even if they moved after the decision.
Its current QA-only artifact requires `rendered_ui_checked=true` for PASS.

The QA-only browser step opens the protected child owner's bot page
with an in-memory bearer token scoped to same-origin read-only API requests.
It checks the rendered `PaperExitEvidence` values and timestamps against the
saved exit projection without uploading DOM, screenshots or tokens. The
previously published production artifact predates this step and remains PARTIAL.
The inactive QA child can be redirected by the unrelated onboarding guard.
For the Paper-exit and source-time display checks only, the protected browser may answer the
exact GET `/api/onboarding/status` with a fixed completed-navigation response;
all bot, trade and exit evidence still comes from real owner-scoped GETs. The
artifact marks this override. This does not test onboarding or its API.

## Local contract checks

`pytest -q backend/trading-tool-backend/backend/tests/test_qa_trader_gate_invariants.py`

`pytest -q backend/trading-tool-backend/backend/tests/test_protected_btc_pair_score_continuity.py backend/trading-tool-backend/backend/tests/test_protected_paper_exit_reconciliation.py`

These tests use synthetic values only. They verify that a copied pair score,
missing outage reason, cross-owner row, Live execution, undated source,
incorrect cashflow or missing UI field yields a fixed failure subcode without
leaking values. They do **not** constitute a production test.
