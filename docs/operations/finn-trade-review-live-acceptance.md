# FINN trade-review live acceptance

Status: release-candidate QA scope; no production verdict is implied by this document.

## Release identity and ownership

Run this matrix only after the preceding active FINN release has an independent
verdict and the trade-review candidate has been deployed. Build records the
candidate SHA, successful CI and Auto Deploy, HTTP 200 from backend health and
frontend build info, and the exact matching SHA from both public surfaces in
`docs/agents/FINN_RELEASE_STATUS.md`. Independent QA verifies those identities
again and owns the authenticated runtime verdict. Build must not run the
protected QA workflow or inspect QA-only credentials and fixtures.

The current protected `FINN_QA_USER_ID` fixture has no exchange keys. It can
support an authenticated read-only check, but it cannot prove linked Bitvavo
or Bybit behavior. A linked test account and permission for QA to use it must
be established explicitly under the fixture contract before exchange cases
are marked tested. Do not select an ordinary user by heuristic or put an
exchange key, token, screenshot, note or transaction payload in QA artifacts.

Bitvavo's [REST API permissions](https://docs.bitvavo.com/docs/rest-api/introduction/)
require both View access and Trade digital assets to retrieve order and trade
history. This importer calls the private trades endpoint, so a View-only key
cannot prove the Bitvavo fill path. Trade permission also authorizes orders
outside this import route. Use a new key only with explicit owner authorization
and a bounded QA account and IP scope; never reuse a key disclosed in chat.
Without that authorization, mark live Bitvavo import **untested** while
continuing the other acceptance cases. The QA import route itself must make
no broker order calls regardless of key permissions.

## Acceptance matrix

QA records each case as passed, failed or untested, with the deployed SHA,
request status, bounded timing, relevant response fields and a sanitized
artifact hash. A case is not passed merely because its endpoint returns 200.

| Area | Required observation |
| --- | --- |
| Access | A permitted owner can list and open their reviews. Another authenticated owner cannot read the dossier, chart, screenshot, messages or lesson. A disabled rollout account gets the documented disabled state. |
| Paper closure | A buy and a partial sell remain open. One review appears only after the residual position reaches zero. Multiple buys and partial sells form one dossier with the expected fill count, costs and result. A replay or refresh does not create a duplicate. |
| Exchange import | On an explicitly linked QA account, Bitvavo and Bybit spot imports show source status and paginated executions. Repeated syncs do not duplicate fills. Unavailable or incomplete provider history is reported as such, without claiming a complete account position. Import must not place an order. |
| Spot attestation | A partial exit is rejected as a completed trade. The user can select matching buys, added buys and partial exits that end at zero, confirm closure and create one dossier. The dossier distinguishes imported execution facts from user-confirmed closure. Duplicate or foreign fills and cross-account selection are rejected. |
| Derivatives | Bybit linear/inverse shorts and longs, including a partial close, remain open until fully closed. A complete episode can be user-confirmed, persists once under retry and carries its fee, funding and native PnL availability labels. A truncated evidence window never becomes provider-proven closure. |
| Dossier | The original plan appears only when a historical snapshot exists. A note and one confirmed lesson survive reload. A missing screenshot leaves the dossier available for later completion. Upload, read and delete of a PNG work for its owner and fail safely for another owner. |
| FINN analysis | FINN uses the final trade and available screenshot, identifies evidence separately from user explanation and its own interpretation, and never claims plan discipline without a plan snapshot. One concrete lesson can be confirmed by the user. Questions and answers persist in the same dossier. |
| Learning | A later trade can retrieve an earlier user-confirmed lesson as reflection context. It does not treat that lesson as the later trade's original plan or as execution evidence. Editing evidence makes prior analysis or messages visibly stale where applicable. |
| General coach | FINN's normal conversation can refer to an owner-visible, confirmed earlier lesson and link back to the right closed dossier. It does not surface another user's lesson or propose a trading action solely from that lesson. |
| Safety and UI | The web flow works at desktop and narrow mobile width, including loading, incomplete history, provider failure and retry states. Reflection and analysis cause no broker order, live bot activation or unintended mutation. User-visible wording makes any user-confirmed closure and unavailable PnL clear. |

## Evidence boundaries

The protected `trade_review_preflight` profile checks only the authenticated
list and exchange-source read routes on the bound QA fixture. It accepts no
manifest or fixture actions, exports no trade data, and reports only HTTP
status, schema checks and timing. A passing preflight is not acceptance of
the cases above. Those require a manual independent QA run or additional
dedicated protected coverage. Local synthetic/provider tests are Build
evidence, not a substitute for linked-account or authenticated UI evidence.

If an exchange test account is unavailable, QA may still report results for
Paper, access, dossier and coach cases, but the overall linked-exchange claim
remains **untested**. If a safe Paper fixture with a known complete trade is
unavailable, that runtime case also remains **untested**; QA must not create
live orders or repurpose normal user trades to fill the gap.

Current implementation bounds should be checked explicitly in acceptance:
spot attestation accepts at most 500 selected fills; the Bybit derivative
candidate projector may omit episodes longer than 10,000 executions. These
bounds must appear as coverage limits in any verdict claiming support for
"every trade".
