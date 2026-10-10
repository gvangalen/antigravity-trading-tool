# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CI_VALIDATED_PENDING_DEPLOY`; independent authenticated live acceptance remains pending. |
| Goal | Stop the Analyse page's React-runtime reload loop and give FINN readable source moments for its first price/score response without changing Score 2.0 freshness decisions. |
| Candidate branch | `codex/finn-chat-react-render`. |
| Previous live SHA | `feb0b1ebe03c1c0acaee520a5004ffb0ef8dc49f`. Independent QA replayed the exact FOMO question once: FINN answered without a proposal or action. The browser also reloaded automatically and logged React error #185; the first price/score answer still showed milliseconds. |
| Last updated | 2026-10-10. |

React error #185 denotes excessive state updates. The frontend recovery script certainly treated every minified React error as a stale-cache event and reloaded the page. The Analyse workspace also supplied newly allocated empty watchlist and score-weight objects during incomplete responses; those render dependencies have been stabilized and weight state writes now stop when values have not changed. Without the original browser component stack, the exact state loop cannot be attributed to one component from this evidence alone. Runtime errors will now remain visible instead of triggering a cache purge and reload; chunk-loading failures still use cache recovery.

The FINN score adapter now displays component source moments to whole seconds, and the Responses read boundary does the same for the market snapshot. Tool freshness is still calculated from the unrounded provider moment. Stored measurements, scores and bot decisions are unchanged. Focused tests cover both model-facing timestamps and the unchanged market-source freshness input.

Local validation: backend **3133 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests, release-hardening tests and `audit:high` passed. The isolated worker-driven action matrix passed **16/16**, with zero broker orders, live-trading calls or production connections; artifact `.local-finn-parity-artifacts/react-score-display-action-final.json` SHA-256 `e6b6c0924eacc00bd6b4bb774e3bbfd1538b09bc65c3752257f2dbb1b84ed705`. Real-provider Luna selector development passed **18/18**; artifact `.local-finn-parity-artifacts/react-score-display-selector-development.json` SHA-256 `db47325f2e6dceced92d2dc4d26b35de5f13cd3b85466ae3c1bdcf5b52e32aaa`. The first full regression was **108/109** because `reg-ambiguous-improvement-variant` chose `evaluate_plan` instead of `clarify_request`; that red artifact remains recorded. Three immediate isolated replays of that case chose `clarify_request` (**3/3**). The complete rerun passed **109/109** with zero provider, schema, parse or timeout failures; artifact `.local-finn-parity-artifacts/react-score-display-selector-regression-rerun.json` SHA-256 `d5c1264a2e08d2fc109ce4d7ee6f4a25ec68a32bb9fc4adc5826ad78c8cf643c`. Candidate [CI run 38050844986](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38050844986) passed all five jobs. Build did no authenticated production QA.

Independent QA should replay the price/score → FOMO conversation once and monitor for a reload or React error, including a partial Analyse response. It should check that the first price/score answer and the DXY answer show readable source moments. The fresh-price/missing-score transient state remains opportunistic; no score or trade should be manufactured to trigger it.

## Previous Release (FOMO turn and source display)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate and main CI, Auto Deploy, and public deployment identity passed. Authenticated live acceptance remains pending. |
| Goal | Diagnose the intermittent first-turn FOMO failure, verify the fresh-quote/missing-score boundary, and present DXY with the same two-decimal precision and readable source time as Analyse. |
| Candidate branch | `codex/finn-fomo-turn-and-display`. |
| Candidate implementation SHA | `2d6ae86725a76a68babd9313318afab3287d9c49`; [PR #138](https://github.com/gvangalen/antigravity-trading-tool/pull/138) merged as `03e0c97589de6ec9eae84a492437138ffea391e7`. |
| Verified deployed SHA | `03e0c97589de6ec9eae84a492437138ffea391e7`; backend health and frontend build info each returned HTTP 200 and this exact SHA. A later status-only deployment can change the public SHA without changing the implementation. |
| Previous live SHA | `3ae758d3a4fc1a1f7559764f49ea38437c6382c0`, independently tested: price and valid Market score were distinguished, but the first FOMO turn failed once; a repeat succeeded. The missing-score state was not present in that live run. |
| Last updated | 2026-10-10. |

The original production FOMO run was located through a read-only, metadata-only runtime-store query using the exact user-supplied prompt and UTC window. It terminalized `unavailable` with `responses_tool_round_limit` after **five completed read tools** in about 12 seconds. The immediate retry completed after four read tools. This was neither browser polling exhaustion nor the 40-second lifecycle deadline. The request preprocessor also classified the explicit “geen voorstel” coach question as `create` because it mentioned both “voorstel” and “setup”; that disabled the read-only continuation boundary. The repair treats a declined proposal as read-only unless an affirmative earlier mutation exists, and permits one answer-only Responses round after five successful read calls on a read-only coach turn. No further tools or actions are allowed in that final round. The model still owns the answer, and action requests retain the original round limit. The frontend now writes only run-ID, terminal status and error code to the console for failed/unavailable runs, and a distinct diagnostic for polling exhaustion. These diagnostics are not added to FINN's chat answer.

The model-facing DXY snapshot now shows two decimal places and source timestamps to whole seconds. Stored readings, Score 2.0 calculations and bot decisions are unchanged. A deterministic local test covers a four-minute-old Price observation with a saved Market score that still refers to older evidence: the price source is fresh, the Market score remains unavailable pending rebuild, and no benchmark is fabricated. This is **local proof**, not an authenticated production observation of that transient state.

Local validation on the final repair: backend **3131 passed, 3 skipped**. Targeted regressions verify that the exact FOMO request is read-only, that an explicit mutation remains a mutation, and that Luna can answer after five completed reads without a sixth tool. The rebuilt isolated worker-driven safe-action matrix passed **16/16**, with zero broker orders and live-trading calls; artifact `.local-finn-parity-artifacts/fomo-round-final-safe-action-16.json` SHA-256 `a352833ff82a8106a1e5f6b15833b8749647a66d1f5a8690bce9de7357369be5`. A local synthetic real-provider replay of the exact FOMO wording selected **five read tools and then one tool-free answer round**, completing without a proposal in 12.1 seconds; artifact `.local-finn-parity-artifacts/market-score-fomo-exact-probe.json` SHA-256 `42334071ffe16769b220c38f391485c1bf02200609badc4c618d4739003f2fcc`. Real-provider selector development passed **18/18**, SHA-256 `bfffeb5e5606939ffb07cdffb89b787b9f6d7d3f18fecc8945eef0367f9259e8`, and regression passed **109/109**, SHA-256 `d810f4398bfc29406308057888fd17dedb7520c3a570a2e7c6f580547063c0bd`, with zero provider, schema or timeout failures. Earlier candidate regression runs with one elliptical-reformulation mismatch (**108/109**) remain recorded as red diagnostics. A broader 37-case legacy parity harness was also red: it expects selector `operation_id` metadata on model-led read turns and reported a separate delete-operation mismatch. That harness is not the safe-action matrix and needs separate contract maintenance. Frontend build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed before the backend-only repair. Candidate CI run [38037988431](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38037988431) and main CI run [38038141442](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38038141442) each passed all five jobs. [Auto Deploy run 38038244700](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38038244700) succeeded. Build verified backend health and frontend build info returned HTTP 200 with the same deployed SHA; Build performed no authenticated production QA.

Independent QA should replay the exact score → FOMO conversation and inspect the new failure diagnostic if it recurs. QA should also verify DXY presentation and opportunistically check a live fresh-price/missing-score state without manufacturing scores or trading.

## Previous Release (market score evidence parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live QA remains pending. |
| Goal | Keep a fresh Price measurement distinct from a verified Score 2.0 Market score, and avoid exposing raw status codes or binary-float artifacts in FINN's explanation. |
| Candidate branch | `codex/finn-market-score-evidence-parity`. |
| Candidate implementation SHA | `8d1422075732a4fe1869acc41b20d3489f290eec`; release evidence commit follows. |
| Candidate merge SHA | `caac418eb9541c6e9107511ef123dbbaad4cc602` ([PR #136](https://github.com/gvangalen/antigravity-trading-tool/pull/136)). |
| Production SHA | `caac418eb9541c6e9107511ef123dbbaad4cc602`, observed on both public surfaces. This status-only update creates a later SHA; verify current identity before authenticated QA. |
| Previous live SHA | `d3b8c038a69730f9cc3f05206235e612051e74e5`, independently tested: the DXY freshness fix passed; Price quote freshness and Market score eligibility contradicted each other. |
| Last updated | 2026-10-09. |

The code-level cause is that `get_market_snapshot` used the database receipt time as the quote's `as_of`, while Score 2.0 verifies a saved daily score against the configured per-owner indicator measurements and evidence. A failed score verification was always called `stale_source`, even when the measurement itself was fresh and only the score rebuild or evidence match was pending. Without the cited live run trace, the exact failed predicate on that turn is not proven. The repair uses the quote's provider observation time, gives score verification and per-indicator source freshness separate statuses and plain explanations, and makes both read tools available to the model when a question compares them. The macro tool rounds the model-facing DXY value to six significant digits; storage and scoring keep their original precision. The strict Score 2.0 bot gate, score formula, trading permissions and model answer ownership are unchanged.

Measured local evidence: backend **3123 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests passed; `audit:high` exited successfully with one moderate Next.js advisory. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16** on the final code, artifact `.local-finn-parity-artifacts/finn-market-score-evidence-release-rerun.json` SHA-256 `644fb527d22196b39140b968ebca8cb1882060879b5214f54e0d89993b47ea6b`. An earlier local matrix had one strategy-clarification miss (15/16); that diagnostic is retained and is not represented as green. A synthetic local two-turn real-provider probe on a fresh quote with an unverified Market score selected both read tools, described the quote as fresh and the score as pending verification, and emitted neither a raw status code nor a made-up score; artifact `.local-finn-parity-artifacts/market-score-two-turn-final.json` SHA-256 `018e6698d7132aeca38a43d429876117081bb70477432d01965dd9299f4b3ec1`. Real-provider Luna selector development selected the expected operation **18/18**; regression selected it **109/109** with zero provider, schema, timeout, parse or validation failures. Artifacts SHA-256 `668be1f5b4f1b73b29958e87f9d2aca18f32e66aaa98bc453180f94bb46b3848` and `fdd2a000884cf893205fd3a54c712fbfe5371968b98453ac3f1c4eda1671ff27`. The regression has one additional conversation-reference/missing-input mismatch on a live-bot-activation case (**108/109** on those two metrics); the same case and result occur in the previous deployed release's regression artifact. That high-risk action path is outside this score-read repair and remains policy-denied. Build performed no authenticated production QA.

After deployment, independent QA should ask FINN to compare the Price measurement's source time with the current Market score in Analyse, then ask a FOMO follow-up. A recent quote and unavailable score must be explained separately, with no raw `stale_source` label, full binary-float DXY value, invented combined score, proposal or order. Check the actual stored score and quote source moments; a truly old measurement should be called old, and a later valid rebuild should allow the score. This candidate does not by itself prove which score verification predicate failed in the original live run.

[Candidate CI run 37983016232](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37983016232) and [main CI run 37983274619](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37983274619) passed all five jobs. [Auto Deploy run 37983491784](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37983491784) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `caac418eb9541c6e9107511ef123dbbaad4cc602`. Build performed no authenticated production QA.

## Previous Release (macro freshness parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live QA remains pending. |
| Goal | Align the separate FINN macro snapshot's source freshness with Score 2.0 so the same DXY observation cannot be fresh in Analyse and stale in a follow-up tool result. |
| Candidate branch | `codex/finn-macro-freshness-parity`. |
| Candidate implementation SHA | `158783fdb9840a75fe46112cd11e54d5ab3332da`; status evidence commit follows. |
| Candidate merge SHA | `88b3c4e54f67920a04f3a62e90407cd1bf56c9ea` ([PR #134](https://github.com/gvangalen/antigravity-trading-tool/pull/134)). |
| Production SHA | `88b3c4e54f67920a04f3a62e90407cd1bf56c9ea`, observed on both public surfaces. This status-only update creates a later SHA; verify current identity before authenticated QA. |
| Previous live SHA | `7d81881d7c5f131016ab8f66ead3d76d0ab8c956`, independently tested: score/FOMO continuity passed; separate macro snapshot freshness contradicted the Score 2.0 DXY source moment. |
| Last updated | 2026-10-09. |

Root cause in code: `read_macro_snapshot` fell through to a generic six-hour tool TTL, while Score 2.0 checks each macro observation using its own release window (four days for DXY, 75 days for monthly inflation/rates). The macro adapter now reports each indicator's `source_status` using the Score 2.0 source rule and supplies a snapshot status only when all measured indicators agree. A mixed snapshot is `unknown` at bundle level; each source retains its own status. No response copy, model override, score calculation, bot rule or action contract changed. Without the specific live run trace, this explains the deterministic mismatch in the deployed code but does not prove that the cited run used that exact tool call.

Measured local evidence: backend **3120 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests passed; `audit:high` exited successfully with one moderate Next.js advisory. Isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16** with zero production connections, broker orders, or live trading calls; artifact `.local-finn-parity-artifacts/finn-macro-freshness-action-matrix.json` SHA-256 `555bfcf0a4f9d1424426d5a3146f4b0c0eda9b43a330904ed729c03ec6fa4dde`. Real-provider Luna selector development passed **18/18** and regression **109/109** operation matches, with zero provider, parse, schema, timeout or validation failures; artifacts SHA-256 `7788cce8f4a23013f60da0e7ff0ff43f07acaba50e15b37542a6d69306325a23` and `ba57e927e75b303591b69387eef682af90dc5ba30f2551a67c3c6d77f52a046a`. A separate synthetic local two-turn real-provider probe read current ETH scores, then the separate DXY macro snapshot; Luna called `get_current_asset_scores` followed by `get_market_snapshot` and identified the same 12-hour-old DXY measurement as fresh in both answers. Artifact `.local-finn-parity-artifacts/macro-freshness-two-turn-probe.json` SHA-256 `ba65b151a6fdb4115bfde24ac6c4f2f078dab15f9233e75ef331244d11932409`. Build performed no authenticated production QA.

After deployment, independent QA should repeat the same score-read → separate macro-snapshot question on the deployed SHA. Compare the DXY source moment and status with Analyse, including an actually stale or missing macro source if available, and verify that no trade or bot action is proposed.

[Candidate CI run 37977348735](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37977348735) and [main CI run 37977569308](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37977569308) passed all five jobs. [Auto Deploy run 37977796710](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37977796710) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `88b3c4e54f67920a04f3a62e90407cd1bf56c9ea`. Build performed no authenticated production QA.

## Previous Release (score freshness continuity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live QA remains pending. |
| Goal | Keep Score 2.0 source freshness consistent between a score answer and an immediate FOMO follow-up, and prevent incomplete selector JSON from ending an otherwise valid turn, without replacing the model's coaching answer. |
| Candidate branch | `codex/finn-score-freshness-continuity`. |
| Candidate implementation SHA | `f8dd00a5e00e97299d432073cd12191be1faeedd` (score continuity `2cf327c6a39b04189ae85a8dd07149ecb6245e67`); status-only commit will have a later SHA. |
| Candidate merge SHA | `aa03bdd5399b916bdc8a47dd7d06b6a743464708` ([PR #132](https://github.com/gvangalen/antigravity-trading-tool/pull/132)). |
| Production SHA | `aa03bdd5399b916bdc8a47dd7d06b6a743464708`, observed on both public surfaces. This status-only update creates a later SHA; verify current identity before authenticated QA. |
| Previous live SHA | `9d5fd3e16e8f3166e54cfd5cebcf161075d05e2d`, independently tested with a contradictory same-day freshness explanation; confirmed strategy-rename continuation passed. |
| Last updated | 2026-10-09. |

The score read now distinguishes its daily report date from the UTC moment when FINN checked component-source freshness. That check moment is preserved with the verified evidence for the next turn. The model-led coach is told to re-read the score tool before making a new current-score claim; it may answer general FOMO coaching without a freshness claim. The selector's strict JSON budget was raised after two full regression runs each found an incomplete response on the same short MACD question. A single retry is allowed only for `incomplete_structured_response` without a provider refusal; the original schema and registry validation still apply. No fixed answer copy, action contract, scoring formula, bot execution, or trading permission changed.

[Candidate CI run 37973332390](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37973332390) and [main CI run 37973567473](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37973567473) passed all five jobs. [Auto Deploy run 37973734565](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37973734565) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `aa03bdd5399b916bdc8a47dd7d06b6a743464708`. Build did not perform authenticated production QA. Independent QA should replay the score-read → FOMO follow-up on the deployed SHA, compare FINN's source moments with Analyse, and verify that an unavailable score still remains unknown rather than becoming stale or zero.

Measured local evidence so far: backend **3116 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests passed. `audit:high` exited successfully with one moderate Next.js advisory. The final worker-driven action matrix on the rebuilt API/Celery stack passed **16/16**, artifact `.local-finn-parity-artifacts/freshness-action-matrix-release.json` SHA-256 `e86b5b9c24be2f3a42b4caff7735f0456f2dec81d47cb18595465b011ca9ce9c`. A synthetic local real-provider Luna Responses probe read scores in the first turn and re-read them for **2/2** differently worded FOMO follow-ups; neither answer called the freshly checked scores stale or turned scores into a buy instruction. Artifact `.local-finn-parity-artifacts/freshness-followup-final.json` SHA-256 `245e8250331241fd658e475f4b695d08f17d32d885ae03b618ee3fe1279d2380`. The isolated API/Celery historical-score check passed **2/2 turns** against Score 2.0's current-only contract: a two-day-old stored row did not populate current scores or produce an entry signal. Artifact `.local-finn-parity-artifacts/freshness-date-runtime-final.json` SHA-256 `4b83268307edeebd41dcbe17765d84858ac59e5bb00d2f320d4d982eb52b3db9`. Two 109-case selector runs each had **108/109 operation matches** because `s609-02` returned incomplete structured output. A direct trace captured `response_status=incomplete`, `incomplete_reason=max_output_tokens`; another showed `response_status=completed` with invalid JSON. With the new bounded selector transport, that case passed **12/12** direct real-provider attempts. The final real-provider selector development passed **18/18**, artifact SHA-256 `b3eea83df15d0284fc3223614be30a1d28d86bbb8b06de979f33c7bf98d1578a`; regression passed **109/109** operation matches with zero provider, parse, schema, timeout or validation failures, artifact SHA-256 `1aac376abd93a4accbe4b22956842b5d013f5472fba8b0b28cae6a275e69018c`. The published `s609-16` still has no verified bot identity, so its separate conversation-reference and missing-input metrics are 108/109; no live-bot activation is inferred. A third diagnostic regression was blocked by the local per-case limiter after repeated targeted calls; the eval runner now isolates the limiter per run without changing production limits. The red diagnostic runs are retained, not counted as passes. There is no authenticated production QA claim for this candidate.

## Previous Release (confirmed strategy continuity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Independent authenticated live QA remains pending. |
| Goal | Preserve the confirmed strategy identity and verified rename across FINN follow-up turns; align daily score freshness with Score 2.0 and expose per-indicator source moments. |
| Candidate branch | `codex/finn-confirmed-action-continuity` ([PR #130](https://github.com/gvangalen/antigravity-trading-tool/pull/130), merged). |
| Candidate implementation SHA | `4fcafaa612ed438b6790e90b3d84c3467faf61a7`; candidate head also includes this status update. |
| Previous live SHA | `859b0e6feb129cfc38900324ba5225c10ba59e0c`, independently tested with a broken post-confirmation strategy reference and inconsistent freshness explanation. |
| Candidate merge SHA | `b0854580701e02a0bead70c33fa12f508fa51312`. |
| Production SHA | `b0854580701e02a0bead70c33fa12f508fa51312`, observed on both public surfaces. This status-only update creates a later SHA; check current public identity before live QA. |
| Last updated | 2026-10-09. |

The confirmed strategy postcondition now supplies the owner-scoped strategy and parent setup to the next read. A confirmed rename preserves the verified old and new names; fields still require a fresh saved-object read. The daily score tools compare a report **date** with the current UTC report date while Score 2.0 independently verifies each indicator source. Their typed result now carries the configured indicators' source moments. The model is asked to translate `fixed` to a user-facing fixed amount. This batch does not change bot execution or trading permissions.

Measured local evidence: backend **3111 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests passed. `audit:high` exited successfully with one moderate Next.js advisory. The isolated PostgreSQL/Redis/API/prefork-Celery action matrix passed **16/16**, including a new same-conversation read after a confirmed strategy update; zero production connections, broker orders, live trading calls and live bots. Artifact `.local-finn-parity-artifacts/finn-action-continuity-final.json`, SHA-256 `b65cfa70f39be8e2dc1af3478af641d0828e346d1d5446297aa53a617537bd34`. A separate local real-provider rename → confirmation → follow-up probe completed, read the owner-scoped strategy, and named both old and new strategy names; this is not production QA.

Real-provider Luna selector development passed **18/18**, artifact SHA-256 `381b11ccf2448b346c945ebab068098a474d7b88bce6741ec0cadcbf38aa12fc`. Regression passed **109/109**, artifact SHA-256 `bb89abc3cb8fc982834e93cf1502b0f9c81d8949378699f6ac003671affb6c92`. Both runs had zero provider, schema, parse, validation and timeout failures. The exact reason for the old live freshness contradiction cannot be proven without that run's trace; the new source moments and date semantics make the distinction testable in the next independent live run.

[Candidate CI run 37965385737](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37965385737) and [main CI run 37965609420](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37965609420) passed all five jobs. [Auto Deploy run 37965849977](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37965849977) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `b0854580701e02a0bead70c33fa12f508fa51312`. Build performed no authenticated live QA.

## Previous Release (Luna internal-model unification)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live acceptance remains pending. |
| Goal | Use Luna with reasoning `none` for FINN V2's remaining internal Responses calls, and remove redundant proposal and answer overrides that block valid coaching and drafts. |
| Candidate branch | `codex/finn-internal-model-unification` ([PR #128](https://github.com/gvangalen/antigravity-trading-tool/pull/128), merged). |
| Candidate implementation SHA | `bad6705616c61dd3c35ac906a0fc81c2762f95d9`; this status update will have a later SHA. |
| Candidate merge SHA | `18099031e4abee69535c309032a40f1e22fba4a8`. |
| Production SHA | `18099031e4abee69535c309032a40f1e22fba4a8`, observed on both public surfaces after successful Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Last updated | 2026-10-09. |

The FINN V2 auxiliary Responses classifiers, semantic verifier, hard-claim boundary, repair path and structured operation selector now use the configured Luna model and reasoning `none`. Proposal relevance checks only whether the user requested a persistent change; owner-scoped target resolution, contract validation and explicit confirmation remain the write boundary. An inconclusive auxiliary relevance call cannot veto a confirmation-gated draft. The answer boundary no longer treats a coach's question about which risk a rule should address as a promised trading outcome.

Measured local evidence on the isolated PostgreSQL/Redis/API/prefork-Celery stack: backend **3105 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests, and high-severity audit passed. The final worker-driven action matrix passed **16/16** with zero production connections, broker orders, live trading calls or live bots; artifact `.local-finn-parity-artifacts/full-action-matrix-final-verified.json`, SHA-256 `f68e7d6b2e7460d79ede50aa8e70c6b60a0383daa0a1713c1b108a141875a777`. Real-provider model-led coach gates passed **12/12 turns and 3/3 action lifecycles** on both baseline and alternate NL/EN/DE conversations; artifacts `.local-finn-parity-artifacts/model-led-coach-baseline-final.json` SHA-256 `d2181e71a5c3c79cd774d0da4163905c44a4833894df5578e0aed049b3caf423` and `.local-finn-parity-artifacts/model-led-coach-alternate-final.json` SHA-256 `60afb0b462e6dbe8213ec34458bae4992ed4cc99246246f836504576015e7be5`.

Real-provider selector development reached **18/18 operation matches** with zero provider, schema, parse, validation or timeout failures; artifact `.local-finn-parity-artifacts/selector-development-final.json`, SHA-256 `1bb1689d2286d5e994f27a1a377f513f4d6bf4d86d077e35ab59a1d90c2e5fc6`. Regression reached **109/109 operation matches**, with the same zero failure rates; artifact `.local-finn-parity-artifacts/selector-regression-rerun.json`, SHA-256 `6ee88d435d5bd6a071a1567f052cf34186f3b6f573f60f9447ee5b5dab9952d5`. Its conversation-reference and missing-input submetrics are **108/109**: published case `s609-16` asks to activate the “discussed bot” without a verified bot in the case context. The selector keeps `bot_id` missing instead of projecting an unverified target. This mismatch is recorded, not counted as a safe live-bot activation or a fully matching selector case.

Build has not performed authenticated production QA. After deployment, independent QA should verify the explicit saved-object mutation and multi-turn coach paths, effective model provenance where observable, and normal confirmation and Paper boundaries on the deployed SHA.

[Candidate CI run 37944002055](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37944002055) and [main CI run 37944248647](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37944248647) passed all five jobs. [Auto Deploy run 37944423808](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37944423808) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `18099031e4abee69535c309032a40f1e22fba4a8`. Build performed no authenticated live QA.

## Previous Release (unified FINN batch)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; the unified FINN batch and its production migration repair passed candidate/main CI, Auto Deploy, and public backend/frontend SHA checks. Authenticated live acceptance remains pending. |
| Goal | Make FINN the only user-facing trading coach: retire unused legacy assistant, insight, reflection, and flow-registry paths; give chat, Today, reports, web, and mobile the shared FINN context; preserve Score 2.0 semantics and Paper-bot execution boundaries. |
| Candidate branch | `codex/finn-unify-deploy-migration` (repair on top of merged PR #125). |
| Candidate implementation SHA | Original batch `8a5f4d34e460cff80ca50d780013109112b09a36`; repair `5c7065be3e5e20e8aca64054c9d1f434a7e377c0`. |
| Candidate merge SHA | Final repair merge `22dcd339d034541686ff73f65687192cf4894f75`. |
| Production SHA | `22dcd339d034541686ff73f65687192cf4894f75`, observed on both public surfaces after the successful Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. The previous score-freshness candidate was superseded without a recorded authenticated QA verdict. |
| Last updated | 2026-10-09. |

Build removed the obsolete assistant service, gateway, insight endpoint and UI requests, unused flow registry, old reflection and insight tables, and stale assistant-only scripts. The active chat and action routes use FINN V2 visible delivery. Web and mobile read the FINN mission-control briefing rather than a separate insight generator. The existing deterministic bot worker and ScoreToolAdapter remain because they execute Paper decisions and read verified Score 2.0 evidence; they are not separate conversational agents. FINN Today and unified reports use Luna through Responses with reasoning `none`. Auxiliary operation selection and answer-boundary helpers still have separate model calls and are not represented here as a single Luna call.

Measured local evidence: root backend suite **3102 passed, 3 skipped** after the completed removal batch; frontend production build, typecheck, i18n lint/tests, command and proposal tests, and high-severity audit passed; mobile typecheck, lint, web/iOS/Android bundle smokes passed (lint emitted existing warnings). A fresh isolated PostgreSQL/Redis/API/prefork-Celery stack migrated without the retired tables. The worker-driven safe-action matrix passed **16/16** with zero broker orders, live trading calls, live bots, or production connections; artifact SHA-256 `51175b894912abd11f00db573c1299a77ab50e4119396f303dc8069ddd64921b`. Real-provider selector development passed **18/18**, artifact SHA-256 `413719de087d1f620b71cb892c4f721bbf947d637ec7173a70057b41bb23109a`; regression passed **109/109**, artifact SHA-256 `2bd8170692b257e46f29bf2d117ac81b9b7ec3af247088ce24e91edef708f095`. Both provider runs had zero provider, schema, parse, validation, or timeout failures. These measurements do not establish authenticated production behavior or an actual score-driven Paper decision.

[PR #125](https://github.com/gvangalen/antigravity-trading-tool/pull/125) merged after all five candidate CI jobs passed; [main CI run 37923006761](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923006761) also passed all five jobs. [Auto Deploy run 37923169943](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923169943) failed twice while dropping `ai_category_insights`: the old production view `ai_master_score_view` depends on that table. The deploy script attempted rollback; its output also reported `pm2: command not found` during rollback. Public backend health and frontend build-info afterward both returned HTTP 200 and the previous SHA `b758871848c71f3fbcbb8b21bd1298796e4f771e`. The repair explicitly drops the unused view before the table. A disposable PostgreSQL instance with the same table/view dependency completed that migration, removed both objects, and passed a second idempotent run. The root backend suite passed again (**3102 passed, 3 skipped**), and the canonical migration plan validator passed.

The repair passed all five jobs in [candidate CI run 37923588806](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923588806). [PR #126](https://github.com/gvangalen/antigravity-trading-tool/pull/126) merged it; [main CI run 37923841838](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923841838) passed all five jobs. [Auto Deploy run 37924024458](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37924024458) succeeded. Public backend health and frontend build-info each returned HTTP 200 and SHA `22dcd339d034541686ff73f65687192cf4894f75`. Build performed no authenticated production QA.

Independent QA, after deployment and user initiation, should test a new-owner onboarding path through FINN Today, chat, saved plans, dated Score 2.0 evidence and daily/period reports; verify no old insight card appears in web or mobile. Check incomplete and complete benchmark cases, one controlled Paper decision, and that actions still require confirmation. No live order. Build did not access the protected QA fixture or sealed holdout.

## Previous Release (score freshness parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate and main CI passed, Auto Deploy succeeded, and backend/frontend public endpoints reported the merge SHA. Authenticated live acceptance remains pending. |
| Goal | Align per-indicator source freshness in Analyse and FINN, show verified score contributions consistently, localize RSI explanation, and distinguish no bot evaluation from data refresh. |
| Candidate branch | `codex/score-freshness-parity`. |
| Candidate implementation SHA | `45b990afb2aca26698ca4be49593fa1870f3367a`. |
| Candidate merge SHA | `36066457fcd9ace139d174425dc6f4c4fa314425`. |
| Production SHA | `36066457fcd9ace139d174425dc6f4c4fa314425`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | `7268ebe8403e70713f88f300ea221ee0c761a1d9`, as reported by independent authenticated QA. |
| Last updated | 2026-10-08. |

Independent QA on the previous SHA confirmed that a new ETH owner receives measured Price, DXY and RSI scores (Market 30, Macro 20, Technical 40, combined 30). The setup correctly did not match because Macro 20 was below its saved floor of 30. QA also found that Analyse called the RSI source current while FINN called the same observation stale; the DXY and RSI detail cards showed no score contribution beside visible category scores; the RSI detail was English in Dutch UI. The new manual Paper bot had no completed decision, so a positive score-driven Paper decision remains unproved.

Code inspection found a six-hour FINN technical-tool TTL against Score 2.0's 36-hour closed-crypto-candle window, string-only timestamp matching for workspace evidence, a frontend contribution read from a different field than its displayed score, hardcoded English RSI explanation, and a bot-card fallback that said data was updating before any decision ran. The candidate uses the shared source-age policy, normalizes UTC evidence moments, derives the visible contribution from verified daily evidence, localizes RSI in all supported languages and labels the no-decision state accurately. It does not change order or bot execution logic.

Measured local evidence on the candidate: root backend suite **3217 passed, 3 skipped**; frontend production build, typecheck, i18n lint/tests, command and proposal tests, and high-severity dependency audit passed. The isolated PostgreSQL/Redis/API/prefork-Celery safe-action matrix passed **16/16**, with zero broker orders, live trading calls, live bots or production connections; artifact SHA-256 `b9f6f34ae4d26544b242ef91cada5ed99d558df2fb03e6bd011023ad73b98426`. Real-provider selector development passed **18/18**, SHA-256 `819fad5b2146f6cd25b20a3596ed1ac1378042e57cb797bb6707b7821f99441c`; regression passed **109/109**, SHA-256 `0cd8ad80b6843603feaede35492177ddad266dd0e68dc65d8d6c362658c75b9c`, both with zero provider, schema, parse, validation or timeout failures. The action matrix completed before the final workspace-only freshness alignment; focused and full backend tests passed afterward. These measurements do not establish production UI parity or an actual Paper decision.

[Candidate CI run 37839499742](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37839499742) and [main CI run 37839789148](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37839789148) each passed all five jobs. [Auto Deploy run 37840033781](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37840033781) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `36066457fcd9ace139d174425dc6f4c4fa314425`. Build performed no authenticated production QA.

Independent QA should repeat the new-owner ETH Price/DXY/RSI flow and compare the *same source observation* in Analyse and FINN. Check each indicator's contribution and NL/EN/DE explanation, plus the bot's initial no-decision label. A positive score-driven Paper decision remains a separate controlled test requiring a matching setup and an actual evaluation run; never infer it from a newly created manual bot.

## Previous Release (indicator history recovery)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; [PR #121](https://github.com/gvangalen/antigravity-trading-tool/pull/121) merged, candidate and main CI passed, Auto Deploy succeeded, and both public surfaces reported the deployed SHA. Authenticated live acceptance remains pending. |
| Goal | Start owner-scoped DXY and RSI history recovery when a preference is saved; fetch enough closed ETH candles for RSI and materialize the indicator before rebuilding scores. |
| Candidate branch | `codex/indicator-history-new-owner`. |
| Candidate implementation SHA | `90b3a426` (includes the direct RSI-add route and crypto-only candle recovery; release evidence commit follows). |
| Candidate merge SHA | `501d1f784f6ae9e9b4dddfbddc822f5a1815f225`. |
| Production SHA | `501d1f784f6ae9e9b4dddfbddc822f5a1815f225`, observed on backend and frontend after Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | `7df6cd6def5638b8af06f40b1dc7572a669adbdd`, confirmed by the user-provided authenticated browser QA. |
| Last updated | 2026-10-08. |

The authenticated new-owner QA on `7df6cd6` found ETH Price 5/5 and Market 30, but DXY 1/5 and RSI without a measurement; the combined benchmark and setup match remained unknown and the Paper bot made no decision. Read-only production worker logs showed that the hourly history job ran, but no targeted history job was queued by the `PUT /macro/preferences` or `PUT /technical/preferences` routes used by onboarding. The hourly sweep is limited to four scopes. Code inspection found that market history stopped at five closed source days even when crypto RSI required 15. This release repairs the configuration-to-worker handoff and makes RSI request 15 closed days. A source or materialization failure leaves a missing score unknown and records a safe reason for retry.

Local evidence: root backend suite **3214 passed, 3 skipped**, log SHA-256 `2719cd9b569c56a61b7b0457f676e750e5543fa7826dc3344c9a9b39135c937c`; frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed; mobile typecheck passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16** with no broker order or live trading call, artifact SHA-256 `15941e21048c937d79c19ad2590e41eb2d0bf8876c6c7817a4855c06a770fcb4`. This matrix preceded the final direct-POST dispatch and crypto-only scoping additions; their targeted API regressions and the full backend suite passed afterward. A synthetic new-owner run using real dated ETH and direct DXY source routes yielded 63 DXY source days, a measured RSI with no pending owner, and after a normal Price refresh verified Market 30, Macro 20 and Technical 40. Real-provider selector development passed **18/18**, artifact SHA-256 `9d3b3c9b2f9eb67e83dacdc7216f3250db8295f701d870e9763bba035e4324ae`; full regression passed **109/109** with zero provider, schema, parse, validation or timeout failures, artifact SHA-256 `a830af17b9ae7e138399a324c9c32519fdbdf4b1249d9c74753f022327c68439`. [Candidate CI run 37832858087](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37832858087) and [main CI run 37833181571](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37833181571) passed all five jobs. [Auto Deploy run 37833369907](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37833369907) succeeded. Backend health and frontend build-info both returned HTTP 200 and SHA `501d1f784f6ae9e9b4dddfbddc822f5a1815f225`. Build performed no authenticated live acceptance. These local measurements do not prove a live positive setup match or Paper decision.

Independent QA should create a new owner, select ETH Price/DXY/RSI, and observe the targeted recovery after preference save. Compare dated source evidence and scores in Analyse and FINN; the three components should either agree or show a specific unavailable state. Only if all sources are fresh should QA examine a positive setup match and a controlled Paper decision; no live order. Build does not use the protected QA fixture.

## Previous Release (score source adapters)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; [PR #119](https://github.com/gvangalen/antigravity-trading-tool/pull/119) merged, candidate and main CI passed, Auto Deploy succeeded, and both public surfaces reported the deployed SHA. Authenticated live acceptance is pending. |
| Goal | Supply real dated DXY index history and crypto RSI from shared completed market candles, preserve source provenance, and expose pending-source failure reasons so fresh owners can obtain complete Score 2.0 components. |
| Candidate branch | `codex/score-source-diagnostics`. |
| Candidate implementation SHA | `7d543f75` (includes source changes, rollback separation and the aligned isolated action fixture); release evidence commit `5d2c4358`. |
| Candidate merge SHA | `74a8c724ecf39125115aea4712a0810784acc188`. |
| Production SHA | `74a8c724ecf39125115aea4712a0810784acc188`, observed on backend and frontend after Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | Public backend health and frontend build-info both reported `ec63e300efa85d633b8b643fd190114b9079417b` with HTTP 200 during this Build turn. |
| Last updated | 2026-10-08. |

The preceding authenticated QA run on `2d1b5950` confirmed a new ETH owner could save a profile and select Price, DXY and RSI. Market scored 30 on 5/5 genuine source days, while DXY had 0/5 and RSI no measurement, leaving Macro, Technical and the combined benchmark unknown. This candidate addresses those missing source paths without manufacturing scores. DXY now uses one direct index time series for both current and historical readings; old derived-basket rows remain separately archived. Crypto RSI first uses completed dated market candles already shared by Score 2.0. Source failures retain a safe category/code in worker diagnostics. A production-positive score, setup match or Paper decision has not yet been observed for this candidate.

Measured local evidence: root backend suite **3208 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity audit passed; mobile typecheck and migration-plan validation passed. The isolated PostgreSQL/Redis/API/Celery action chain passed **16/16**, with zero live bots or non-allowlisted executions after the chain; artifact SHA-256 `1bc8890ee641e3158184075fe5ddef37aff442a9cd0c0e9f151b371e6208e8b1`. Direct DXY history was reachable from the isolated worker and returned 63 genuinely dated closes, last on 2026-10-07. Real-provider selector development passed **18/18**, artifact SHA-256 `aa36d9da2aa088904b2262d01a8dc78b46a42bbe8e4d901f583d87395e7526a4`. A first full regression scored **107/109**, including one provider failure; the sequential complete rerun passed **109/109** with zero provider, schema, timeout, parse or validation failures, artifact SHA-256 `f4af93ef3908a52ca7b48bf53c9477f2c8cee2dc60ec0caf6de385ddcc98bfb8`. The separate 37-case nonsealed diagnostic matrix failed because its original DCA action fixture omitted the now-required amount and its read probes expect legacy operation IDs for freeform answers; this diagnostic is not claimed green. [Candidate CI run 37817577570](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37817577570) and [main CI run 37817832298](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37817832298) each passed all five jobs. [Auto Deploy run 37818042898](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37818042898) succeeded. Backend health and frontend build-info both returned HTTP 200 and SHA `74a8c724ecf39125115aea4712a0810784acc188`. Build performed no authenticated live acceptance.

Independent QA should create a fresh owner, configure ETH Price/DXY/RSI, wait for genuine dated history and an actual rebuild, and compare each indicator's source day, rule and score across Analyse, FINN and the daily report. Confirm that Market, Macro, Technical and the weighted benchmark are either all correctly evidenced or explicitly unavailable, never zero by default. Only with complete fresh data, test one positive setup match and one controlled Paper decision; no live order. Verify old derived DXY measurements do not enter the new direct-index normalization and that a failed source remains pending without a fictitious score.

## Previous Release (current-score parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; [PR #118](https://github.com/gvangalen/antigravity-trading-tool/pull/118) merged, all CI jobs and Auto Deploy passed, and both public surfaces reported the deployed SHA. Authenticated live acceptance is pending. |
| Goal | Repair the new-account profile loading race and make FINN and Analyse use the same verified current Score 2.0 components and indicator evidence. |
| Candidate branch | `codex/score-qa-followup`. |
| Candidate implementation SHA | `104e8a73` (the release-status commit follows this implementation commit). |
| Candidate merge SHA | `ec63e300efa85d633b8b643fd190114b9079417b`. |
| Production SHA | `899b4fbb093e7cfaf627fdaa556e51ea6d55bec4`, observed on backend and frontend after deployment. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | `db89ca94e45459ad11ec92a1a5df73092918d954`, measured as HTTP 200 on both public surfaces on 2026-10-08. |
| Last updated | 2026-10-08. |

The user-provided authenticated browser check on `db89ca94` found that a new account could not pass profile onboarding because choices appeared unresponsive and Save stayed disabled. Build inspected the already open tab without submitting or saving, clicked all six required choices and observed Save become enabled with no browser errors, then reset the choices; that exact click failure did not reproduce. The code did reveal two ways a slow preferences request could strand the form: a late response overwrote choices made in the meantime, and the request's loading flag disabled Save even after all required choices were set. Both paths are repaired, and selected buttons expose `aria-pressed`.

[Candidate CI run 37797515860](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37797515860) and [main CI run 37798271113](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37798271113) each passed all five jobs. The API merge and a status push did not start the normal main-CI event, so `workflow_dispatch` was added to the existing CI workflow, validated with actionlint, and used to run main CI on `899b4fbb`. [Auto Deploy run 37798507546](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37798507546) completed success. Public backend health and frontend build-info both returned HTTP 200 and SHA `899b4fbb093e7cfaf627fdaa556e51ea6d55bec4`. Build performed no authenticated live acceptance.

The same browser report showed Analyse withholding an unverified ETH Market score while FINN still mentioned a dated stored “Market 30.” The current-score tool now uses the owner-scoped source verification behind Analyse; stale components return null with a reason. A separate saved-score tool preserves explicit historical report reads. Market-price snapshots no longer carry a saved score. Analyse's daily indicator rows now project the verified weighted indicator evidence saved by Score 2.0, rather than older row score fields. Other display periods retain measurements but show no unverified legacy score. Five dated Price days alone still do not prove a score if another configured source or the rule-based rebuild is incomplete.

Measured local Build evidence at `104e8a73`: root pytest **3202 passed, 3 skipped**, log SHA-256 `0587ad0b9295508ea7b8908402276a3c0e184c0cdefe7912693f380d7b410a48`; frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity dependency audit passed (one moderate Next.js advisory remains). Mobile typecheck passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16**, with zero broker orders, live trading calls or production connections, artifact SHA-256 `ff388192373baf9a2f0f3dcd54b4f7832c5f3985f7e90b0d5f30285eaedf6bc1`. Real Responses selector development passed **18/18**, artifact SHA-256 `2a77425f88b9950232958670c1d6e75cde4b08cb91489203accf0dc9fdfbcfb2`; regression passed **109/109**, artifact SHA-256 `a9412b9f248b2662d823eee7bf0e92eea0c53e2a1eebd9d5e443d85e7213d64b`, with zero provider, schema, parse, validation or timeout failures. The selector implementation did not change after those provider runs. The isolated stack was stopped after validation.

Independent QA must retest a genuinely new account, including a slow preferences response and successful profile save; compare current ETH scores and individual indicator detail in Analyse with FINN without historical-score leakage; and separately ask for a dated historical report. Record why Price with 5/5 source days is still unscored if the rebuild remains incomplete. A positive benchmark/setup match and controlled Paper decision remain unproven until all configured sources are genuinely complete and fresh. Build has not accessed the protected QA fixture or sealed holdout and has not run authenticated live acceptance.

## Previous Release (Score 2.0 source history bootstrap)

| Field | Value |
| --- | --- |
| Phase | `NOT_ACCEPTED` in the user-provided browser run on `db89ca94`: profile onboarding was blocked and FINN mentioned a stale stored score that Analyse withheld. |
| Goal | Complete Score 2.0 indicator history bootstrap and explicit score rules so a new owner can use genuine existing source days without waiting five days after registration. |
| Candidate branch | `codex/score-history-bootstrap`. |
| Candidate implementation SHA | `c26c676cb54f5b3d1577f40e632d12d0996a70e6` plus release-status commit `d4fc5cc9`; merged as `ac5b70d307c7aa4f0b9682ad5394487139a2f561`. A later status-only commit will create a new SHA without changing score behavior. |
| Production SHA | `ac5b70d307c7aa4f0b9682ad5394487139a2f561`, observed on both public health/build-info surfaces after Auto Deploy. |
| Previous live SHA | `45775a219aba597f74de26c6f92c0c0ebfb5864c`, independently tested before this release. |
| Last updated | 2026-10-08. |

The candidate backfills only genuinely dated, completed Price/Volume and absolute macro observations, rejects generated bucket fallbacks as scores, installs explicit system templates where missing, explains insufficient history in Analyse, and queues an owner score rebuild after history becomes sufficient. A newly configured owner also gets a rebuild when that asset's shared market history was already complete. The prior report fact-parity release remains awaiting its own authenticated QA; this Score 2.0 goal does not count as report acceptance.

Measured local evidence at implementation SHA `c26c676c`: root pytest **3197 passed, 3 skipped**. Frontend production build, typecheck, i18n lint/tests, command and proposal tests, and `audit:high` passed; mobile typecheck passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16**, with zero production connections or broker orders, artifact SHA-256 `dd3d064a555c9ffe5a485efe4beb50b5fc29bbb643d88b0e1a159aae6c4f5514`. Real Responses selector development passed **18/18**, artifact SHA-256 `1970ccb1be76c4f22e59274ab43beff2cbaffd1723b634cb59a178342a21bf95`; regression passed **109/109**, artifact SHA-256 `a36c8566ad310c9d69a39fbfe808939b9eac9fad17d55472caa2f2030ed1f312`. Both reported zero provider, schema, parse and validation failures. The isolated migration plan validator passed. [Candidate CI run 37781959643](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37781959643) and [main CI run 37782332086](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37782332086) passed all five jobs. [Auto Deploy run 37782581346](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37782581346) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `ac5b70d307c7aa4f0b9682ad5394487139a2f561`. The later `db89ca94` browser run is summarized in the active repair release above.

A direct local DXY history fetch returned Twelve Data HTTP 429 because its daily API-credit limit was exhausted. The branch retains an unavailable Macro score and retries later; it does not prove that five DXY days or a positive benchmark will be available to a new production account today. Independent QA must test a fresh account after deployment, record each indicator's dated-day count and rule origin, compare Analyse/FINN/benchmark, and separately verify any positive setup match and controlled Paper decision only when all sources are genuinely fresh. No live order is part of this release.

## Previous Release (report fact parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated report fact-parity QA remains open. |
| Goal | Make daily report score and saved-plan facts agree with Analyse, FINN chat and the owner-scoped shared context. |
| Candidate branch | `codex/finn-report-facts-parity`. |
| Candidate implementation SHA | `45fc260fbb545ef1cf381294f0eb6634c795c203` in [PR #114](https://github.com/gvangalen/antigravity-trading-tool/pull/114), merged. |
| Production SHA | `b89e69262c2b9b12f3af2ae9a55cf67c2418dc83`, observed on both public surfaces after Auto Deploy. A status-only commit will create a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `6d6913ec6236e7695c362d606d65011e3bd02b08`, independently tested and not accepted for report fact parity. |
| Last updated | 2026-10-08. |

Independent browser QA completed new-account onboarding with ETH monthly DCA, a linked €120 strategy and a Paper bot. FINN Today transitioned from a temporary summary to a stored personal briefing that persisted after refresh and genuine relogin. Analyse and FINN chat correctly showed insufficient market, macro and technical scores. The daily report contradicted them by calling market 10/100 and technical 50/100 current and denying a saved strategy and indicator configuration. The positive fresh-score and Paper execution paths remain unproven. This is a `NOT_ACCEPTED` fact-parity result for that release, not a provider identity trace.

Build traced the discrepancy to three report-path faults. The writer passed raw `reported_scores` into Luna even when source status rejected those values. It always stored `active_strategy=None` and empty indicator highlights. The shared context also called Pydantic-v2-only `model_dump()` on the deployed v1 indicator schema, caught the resulting exception and silently labelled a successful configuration lookup unknown. The repair projects only fresh component scores into report input and output, serializes the real indicator schema through FastAPI's version-compatible encoder, writes owner-scoped strategy and indicator facts, and uses typed report sections for score/configuration claims. FINN chat answer control is unchanged.

Measured local evidence: root pytest **3184 passed, 3 skipped**, log SHA-256 `1224074359f9f195c6aee503d826cc7ab16751eaeb148cb779ef09d20c043264`. Frontend production build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16**, no broker orders, live calls, live bots or production connections; artifact SHA-256 `957b47baab5b40921f44f1b5e7fa13242c6613f88a6546480ddaa0c30a9a4502`. Real-provider selector development passed **18/18**, artifact SHA-256 `af6a66304fd5af49c1a863fcfa167388203d5983b499be1ddcec184f3bece7e0`; regression passed **109/109**, artifact SHA-256 `4f2f1fdfd2543c939159ce82ccd6159b6d3fe091fd8249b7d5a3644db830fc84`, with zero provider/schema/parse/validation failures. A direct local Luna Responses report over a synthetic database user produced eight nonempty sections, retained configured indicators and saved strategy facts, and kept unverified scalar scores null. The local bootstrap `daily_reports` table lacks historical production report columns, so a direct SQL persistence probe failed with `UndefinedColumn`; the task-to-repository mapping is covered by the focused regression, but the local SQL persistence path is not claimed green. [Candidate CI run 37729841454](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37729841454) and [main CI run 37730025495](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37730025495) passed all five jobs. [Auto Deploy run 37730172154](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37730172154) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `b89e69262c2b9b12f3af2ae9a55cf67c2418dc83`. Independent authenticated QA remains pending.

Independent QA should generate a **new** report after deployment (an older persisted report is not silently rewritten), then compare the same account's Price/DXY/RSI configuration, linked strategy and per-component score freshness in Analyse, FINN chat and the report. With incomplete scores the report must not call raw 10/50 values current or deny configured indicators and saved strategies. The saved report card should distinguish a stored strategy from a current entry signal. Positive fresh-score and Paper decision paths remain separate, unproven acceptance checks. Build did not access the protected QA fixture or sealed holdout.

## Previous Release (unified FINN onboarding and reports)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, merge, Auto Deploy and public SHA checks passed. Authenticated QA remains open. |
| Goal | Replace the separate onboarding/report AI-agent chain with one owner-scoped FINN context, retain measured scoring and Paper execution, and use Luna Responses for FINN Today and reports. |
| Candidate branch | `codex/finn-unified-onboarding`. |
| Candidate implementation SHA | `c94eabf5` plus tracked frontend export commit `cb97ab6c` in [PR #112](https://github.com/gvangalen/antigravity-trading-tool/pull/112), merged. |
| Production SHA | `4d6f4e720a61a4f08989844b3cc238e8a58931ef`, observed on both public surfaces after Auto Deploy. This status-only update will create a later SHA; QA must bind to the current backend/frontend SHA. |
| Last updated | 2026-10-07. |

Build replaced the old onboarding sequence of specialist AI interpretations with measured score tasks, a shared owner-scoped context and one FINN briefing. FINN chat, Today and daily/period reports now use that context or its benchmark service. Daily and period report prose uses `gpt-6-luna` with reasoning `none` via Responses. Saved strategy fields, rather than a separate generated daily strategy snapshot, feed current Paper decisions. The former macro, market, technical, score, strategy and report AI-agent modules and their unused schedules were removed. The older standalone strategy-analysis endpoint and button were removed; strategy cards retain FINN review. Deterministic source collection, score calculation, setup match, report storage and bot safety controls remain. Historical backtesting still reads historical strategy snapshots; this release does not claim point-in-time backtest migration.

Measured local evidence on isolated PostgreSQL/Redis/API/Celery: root pytest **3181 passed, 3 skipped**, log SHA-256 `764c8c3514234fa28aa8bbea3f8ee5ae81a6e440e30efb65a4244ed2cde92813`. Frontend build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed, log SHA-256 `ca9a799af236c02b0b7eb36aa77b1becf64feb067fe3d83c83ad8844308f5942`. The complete local worker-driven FINN action-contract matrix passed **16/16**, with zero broker orders, live trading calls, live bots or production connections; artifact SHA-256 `b26b69d31ee20fc36fa043c68bfd0e143d713ee469d429f99f0d3e9e3dfd7b2b`. Real-provider selector development passed **18/18**, artifact SHA-256 `0be2547579d19f6a5468b04171b6569919586670df7b376580224bb09e152b9e`; full regression passed **109/109**, artifact SHA-256 `069f9fc50e2ec1d904a4af4ac2b5ffaf9d6d0c0ab74a081a5146a9e84d07b670`. A synthetic completed-onboarding account generated and persisted a first Today briefing with `response_source=ai_generated` and Luna usage recorded; synthetic daily and weekly reports produced eight nonempty sections each using Luna. A local Paper-bot decision completed safely on `hold` with no order. These local probes do not establish the cause of earlier production fallbacks or constitute independent live acceptance.

Independent QA should create a new account, complete onboarding and inspect the first briefing's visible `response_source`, `generation_status` and stable saved text after refresh/relogin. Compare the same owner profile, plans and current score status in FINN chat, Today and daily/weekly reports. Test missing and fresh source evidence separately, then one controlled Paper decision; do not place a live order. Verify Dutch, English and German onboarding text and that strategy cards open FINN review without the retired endpoint. Build did not access the protected QA fixture or sealed holdout.

Candidate [CI run 37686545359](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37686545359) and [main CI run 37686811742](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37686811742) passed all five jobs. [Auto Deploy run 37687051695](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37687051695) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` both returned HTTP 200 and SHA `4d6f4e720a61a4f08989844b3cc238e8a58931ef`. The first candidate CI run failed only the tracked frontend export check; the export was committed and the subsequent candidate run was fully green.

## Previous Release (logout and onboarding locale)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local gates, candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated browser QA is pending. |
| Goal | Finish the new-user onboarding handoff by making logout a verified server operation and completing locale-specific onboarding copy in Dutch, English, and German. |
| Candidate branch | `codex/onboarding-logout-i18n`. |
| Candidate implementation SHA | `be610f60` in [PR #110](https://github.com/gvangalen/antigravity-trading-tool/pull/110), merged. |
| Production SHA | `9195019257d5a57270944611bc0d8d86df3e1e87`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `db60d6ea2996a6a835d01eb3dfe92df63163e5e3`, independently tested with a new account. |
| Last updated | 2026-10-07 |

Independent QA on the previous live SHA confirmed a temporary-to-saved FINN Today briefing transition in about 15 seconds, a factually personal stored briefing, and identical final text after a hard refresh. The QA account's ETH monthly day-5 DCA setup, €120 strategy and Paper bot persisted, and onboarding reached 4/4. Logout did not hold in the browser: the same account returned after refresh without a new password, so the saved briefing was not checked after a genuine relogin. Dutch onboarding still displayed “Launch protocol”, “Profile”, “analysis-basis” and “Create bot”. The QA observation does not reveal the logout HTTP status or cookie trace.

Code inspection found that both logout buttons always displayed success and navigated to login, even if the logout request failed. The AuthProvider also erased local state before checking the server response. A surviving HttpOnly auth cookie could therefore restore the same account on refresh. This batch sends logout before clearing local state, bootstraps the existing CSRF cookie when needed, and checks that a fresh `/auth/me` request returns 401 before claiming browser logout. A failed request or surviving cookie leaves the visible session in place with localized failure feedback. The provider also aborts and versions in-flight session checks so an earlier response cannot rehydrate the user after verified logout. Native logout passes its refresh token for revocation. No backend cookie contract was changed, and the exact production failure cause remains unproven without its HTTP trace.

The Dutch onboarding dictionary now covers the reported English labels and related profile, analysis, plan and bot copy. Previously missing bot-step and banner keys were added for all three supported locales, so the screens do not need their English fallback strings for those labels. Locale switching still uses the existing immediate `setLocale`/dictionary path.

Measured local evidence: root pytest **3173 passed, 3 skipped**, final log SHA-256 `a4cf77c0edd6eb8ff0e8258e5ff4b0bab9e9182189ceb985e747d811bd948524`; final frontend build, typecheck, i18n lint/tests, command/proposal tests, focused logout/locale tests, and canonical `audit:high` passed, final build log SHA-256 `6f5ae978c73139bd15f2b8331b20ac6b1f54129d88f863f98c74e96b0a6f98ab`. Isolated PostgreSQL/Redis/API/Celery action-contract matrix passed **16/16**, zero broker orders, live calls or production connections; artifact SHA-256 `2efdeb55c17de20ad8e0db1891c404a56e850c2968a8b8dfb4e995165f8eeda1`. With two separate synthetic accounts on that local API, login and `/me` returned 200, a valid-CSRF logout changed `/me` to 401, and a missing-CSRF logout returned 403 while `/me` stayed 200; a later valid logout cleared that session. Real-provider selector development passed **18/18**, zero provider/schema/parse/validation failures, artifact SHA-256 `7acb05e944824fb83e15e428aef08ebfc71fb4a3f583e77ce57bc20c7da59cdf`. Full regression passed **109/109** with zero provider/schema/parse/validation failures, artifact SHA-256 `78d7db0dfb1d174455b4a2acf1d123ed953d15ec9483af675dc142256265c982`. Build did not access the protected QA fixture or sealed holdout.

Independent QA should sign out from both the avatar menu and profile on a new account, confirm the login page remains logged out after hard refresh and protected navigation, then genuinely log back in and compare the saved FINN Today text. In Dutch, inspect the onboarding shell, analysis, plan, bot and completion screens for untranslated copy; switch to English and German and verify the same labels update immediately. A deliberately failed logout must show an error without falsely reporting success. No live trade is part of this handoff.

Candidate [CI run 37675373786](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37675373786) passed all five checks. Main [CI run 37675671071](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37675671071) passed, and [Auto Deploy run 37675927007](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37675927007) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` both returned HTTP 200 and SHA `9195019257d5a57270944611bc0d8d86df3e1e87`. Build performed no authenticated production QA or production write.

## Previous Release (first FINN Today briefing stability)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ACCEPTED`; independent new-account QA confirmed the temporary-to-saved briefing transition and hard-refresh stability, but could not finish a genuine relogin because logout did not hold. Onboarding copy also remained partly English. |
| Goal | Make the first FINN Today briefing source and generation phase visible on compact and full cards, prevent a stale browser copy from appearing on refresh, and finish the reported Dutch onboarding labels. |
| Candidate branch | `codex/first-briefing-stability`. |
| Candidate implementation SHA | `a531bb98` in [PR #108](https://github.com/gvangalen/antigravity-trading-tool/pull/108), merged. |
| Production SHA | `c27e7c67d4dd191df8e780e9a3fba2a987b1cfc1`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `626744a8fce6b591375874b08e6c2e9d12f71ccf`, independently tested with a new account. |
| Last updated | 2026-10-07 |

Independent live QA on the previous SHA found that the saved DXY/RSI status, monthly day-5 DCA cadence, Paper bot, refresh/relogin persistence, onboarding completion, and Automation route worked. The first FINN Today text was personal and factually consistent, but after refresh the visible card changed from a plan summary to differently worded personal copy. QA could not observe `response_source` or `generation_status` from the UI, so it did not establish whether the latter text was a stored AI briefing or why the transition occurred. Dutch onboarding still showed “Automation” and “Guided onboarding”.

Code inspection shows that the backend intentionally presents deterministic plan copy during `pending`, `queued`, `generating`, and retry states, then the stored AI result at `ready`; it reuses a ready result when its context version matches. The compact FINN Today card did not label these phases. The browser session cache also stored interim and ready first-dashboard responses, which could reappear before the server's current response on refresh. A separate cached insight could briefly fill the compact card before Mission Control loaded. This batch makes the source phase visible in both card views, treats the server's owner-scoped record as the only cache for the first dashboard briefing, and shows a loading state rather than an unrelated insight while the completed account awaits Mission Control. It also supplies the missing Dutch onboarding shell translation and translates the reported navigation and step labels. It does not change the coach's generated answer or claim a specific provider/queue error in the live QA run.

Measured local evidence: root pytest **3173 passed, 3 skipped**, log SHA-256 `5b395ce166d59a3938a9fb5b7ae0685e2373257372aaa0e4b6e29abf8c26cf8f`; frontend build, typecheck, i18n lint/tests, command/proposal tests, focused source-phase/cache/translation tests, and canonical `audit:high` passed, final build log SHA-256 `3664d822a9b5fe2b4a80b2ff0884b81a13d1fa9e2cef6206b444710a793faba3`. Isolated PostgreSQL/Redis/API/Celery action-contract matrix passed **16/16**, with zero broker orders or live calls, artifact SHA-256 `6cf51eba176431b8636d64d71a4491762f0240537a833c0d03f57de7c57f1153`. Real-provider selector development passed **18/18**, SHA-256 `adabcabdbedc147bb9d08ee5fa64956249b8db54c0d1362dbb2e5b5e1d5e9e8a`. The first regression run, concurrent with the action matrix, scored **108/109**: the general plan-audit case `reg-qa-plan-audit-variant` was selected as `evaluate_setup` instead of `evaluate_plan`; provider, schema, parse, and validation failure rates were zero. This red run remains recorded, artifact SHA-256 `d3d83586840aff7a11f9793274accb33f62ee0c0ca9dd378add2bf7061e4dd9c`. The clean sequential full regression passed **109/109**, with zero provider, schema, parse, or validation failures; artifact SHA-256 `3ab86fbd1d16fcb77e77ced045110e08d5dfcb35576c7d098eac1b347826ebd8`. Build has not accessed the QA fixture or sealed holdout.

Independent QA should check the initial temporary label, the transition to the saved-personal-briefing label, and identical saved text on refresh/relogin while the owner plan and evidence remain unchanged. If the saved text changes, capture the displayed phase before and after; a changed context can legitimately require regeneration, while a changed ready result for the same context is a defect. Verify Dutch onboarding shell, navigation and step labels. Build does not access the authenticated QA fixture.

Candidate [CI run 37669378288](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37669378288) passed all five checks. Main [CI run 37669644264](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37669644264) passed, and [Auto Deploy run 37669868130](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37669868130) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` both returned HTTP 200 and SHA `c27e7c67d4dd191df8e780e9a3fba2a987b1cfc1`. No authenticated Build QA or production write was performed.

## Previous Release (indicator configuration and DCA cadence)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ACCEPTED`; fresh-account browser QA on `626744a8fce6b591375874b08e6c2e9d12f71ccf` passed the indicator, DCA cadence, Paper bot, persistence and Automation route checks, but could not verify the first briefing's source/stability and found Dutch copy remnants. |
| Goal | Distinguish saved indicator configuration from unavailable scores in FINN Today; show the saved DCA purchase schedule separately from a chart timeframe in Automation; finish the Dutch onboarding copy. |
| Candidate branch | `codex/onboarding-briefing-dca-cadence`. |
| Candidate implementation SHA | `814b5ed0` (with candidate status correction in `eb591df9`). |
| PR | [#106](https://github.com/gvangalen/antigravity-trading-tool/pull/106), merged. |
| Production SHA | `31bb3e07877ca573f88d579fbf47fa2ba618ca16`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `7eafc957254228f0ebd33580dc5179ec258cc489`, independently tested on a fresh account. |
| Last updated | 2026-10-07 |

Independent QA found that the previous FINN Today card said macro and technical layers were not configured despite saved DXY and RSI configurations without usable scores. The Automation bot dialog used a 1D chart timeframe as purchase wording for a monthly day-5 DCA plan. The bot list repeated the timeframe without the plan cadence. Dutch onboarding still showed English state labels. The first card's live `response_source`, `generation_status`, and `trace.last_error_code` were not captured; this release does not claim to identify a provider or queue fault. No execution-cadence or live purchase outcome was established by that browser test.

The briefing input now carries a separate owner-scoped indicator-configuration status, configured names, and complete-current-benchmark boolean. A lookup failure stays unknown; it cannot be read as an empty configuration. The provider prompt explicitly distinguishes a saved indicator from a usable current score and does not let a historical analysis summary override the current configuration. The briefing contract version changes so older ready text is regenerated. Automation resolves the saved setup for its strategy, presents the DCA frequency and weekday/month day, labels 1D as a chart timeframe, and uses a daily bot spending cap rather than a per-1D purchase amount. Guided bot creation sends the saved DCA cadence and makes its default daily and per-order caps at least the strategy base amount. Dutch onboarding labels are translated. A saved setup is still a plan; this work does not assert that a bot is active or that a purchase is due.

Measured local evidence: root pytest **3173 passed, 3 skipped**, log SHA-256 `d55c947270f1a43856a09a7aeed2ec6cf59028702ea85aff19a8499bc6fd24fc`. Frontend build, typecheck, i18n lint/tests, command/proposal tests, focused onboarding and DCA cadence tests, and the canonical production-dependency `audit:high` script passed. Isolated PostgreSQL/Redis/FastAPI/Celery action-contract matrix **16/16**, zero broker orders or live calls, artifact SHA-256 `62c6046fb4e1683791b7201914f069baeffa520510f782f983946e4c7f82f53b`. Real-provider selector development **18/18** (SHA-256 `212be4fd111708028666ec74605dd2c18c5631c15cde62878fbd28c78a84d151`) and regression **109/109** (SHA-256 `b667490a967f87b01a107ebb8befe42ab569cd876be27b316317440ef45c2f6a`) had no provider, schema, parse, validation or timeout failure. A separate three-response real Luna/none briefing probe with saved DXY/RSI and absent scores did not call them unconfigured (SHA-256 `15a688828eb04b3e81ab30587b072df44c81182fa961b61fc7fdcbab679fd98f`); it is supporting evidence, not a production proof. Build has not accessed the QA fixture or sealed holdout.

Independent QA should check a new account's saved DXY/RSI without scores against the FINN Today text and, if observable, capture `response_source` and generation status. For a monthly DCA setup on day 5 with a 1D chart timeframe, compare the saved setup, Automation form, bot cadence, and bot list after refresh. Confirm the daily cap accommodates the saved amount without implying daily purchases, and inspect the Dutch onboarding labels. Actual bot execution remains outside the read-only onboarding result.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37663553111) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37663790208) passed all five jobs. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37664042646) succeeded for `31bb3e07877ca573f88d579fbf47fa2ba618ca16`. Public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-07. Build did not access the authenticated QA fixture.

## Previous Release (first briefing onboarding follow-up)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity passed; independent authenticated QA is pending. |
| Goal | Keep Automation visible after a saved strategy during onboarding, schedule first FINN Today retries without a browser read, and identify temporary plan copy as temporary. |
| Candidate branch | `codex/first-briefing-onboarding-followup`. |
| Candidate implementation SHA | `c01fcce911aabe21a45cf8d7bc09f2959974c74f` (with the evidence correction in `0ef9b6162a5baf5b02cfd007241876581ebb53a4`). |
| PR | [#104](https://github.com/gvangalen/antigravity-trading-tool/pull/104), merged. |
| Production SHA | `ba247bb2dfdf26b808a98e71b4800fadfa6f83ff`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `e9c0db94671faf513f63ed21ce1783995741339a`, independently tested on a fresh account and not accepted for Automation or first AI briefing. |
| Last updated | 2026-10-07 |

The independent browser test observed Automation briefly before a 37-second dark loading state; refresh recovered it. FINN Today showed text that exactly matches the deterministic DCA template after approximately six seconds and did not visibly change during 45 seconds, refresh or relogin. The response source itself was not observed. The live `response_source`, `generation_status` and `trace.last_error_code` were not captured, so the production provider or queue failure cannot be named. The first retry window in this code is 60 seconds; the 45-second observation alone cannot verify that retry.

`AuthGuard` previously redirected `/bot` while onboarding was incomplete even after a strategy had unlocked Automation. It now permits the saved-strategy Automation route through the authoritative status check and its short-lived user-scoped cache. The first-dashboard worker now schedules a delayed retry through the existing enqueue path after a retryable fallback; a dashboard read is no longer required to initiate that retry. An unparseable provider JSON response is classified as retryable. FINN Today labels deterministic plan copy as temporary while generation/retry is active and identifies terminal fallback as a plan summary. The fallback remains safe and does not imply an AI-generated briefing.

Measured local evidence: root pytest **3171 passed, 3 skipped**; `.local-finn-parity-artifacts/first-briefing-followup-pytest-final.log` SHA-256 `06b55e849f32c45669e0d8c7f65244f5e68c0c26910e50f4870fae15b18bd9ce`. Frontend build, typecheck, i18n lint/tests, command/proposal/onboarding tests and high-severity dependency audit passed; frontend build log SHA-256 `65db30c5a2ca3ea5449644c57e3526f17135b42b34198a75183895f4b7578aaa`. The isolated local API/Celery/Responses safe-action matrix passed **16/16**, with zero broker orders or live trading calls; `.local-finn-parity-artifacts/first-briefing-followup-action-matrix-full.json` SHA-256 `e5457c201b88f6fe47450da44a02d5c3b0a70a9650c739abf3a0b757ca7c473f`. Real-provider selector development passed **18/18** (SHA-256 `ef502054623da8c9004a4c1120a0d7260da4dbfc39f3ef7d781cad46de7b89cd`) and regression **109/109** (SHA-256 `1cd512d0c0f585ced39f7e86ea29a9a290f567c666cc4dcded54230c52ce315f`), with zero provider, schema, parse, validation or timeout failures. The older `finn-local.sh matrix` runner was also attempted but failed because its legacy orchestrator snapshot join found no row on the current `visible_runtime` path; this run is recorded as a runner mismatch, not counted green. The current full action-contract runner is the 16/16 evidence above. The scheduled-retry behavior is covered by a targeted Celery task test; a real production retry on the QA account remains unverified.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37648424412) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37648696393) passed all five jobs. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37648918825) succeeded for `ba247bb2dfdf26b808a98e71b4800fadfa6f83ff`. Public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-07. Build did not access the authenticated QA fixture. Independent QA must test a new account's first Automation transition and FINN Today card, including the displayed source/status label and the delayed retry after its due time; matching text alone is not proof of a provider or queue failure.

## Previous Release (first briefing retry)

| Field | Value |
| --- | --- |
| Phase | `QA_NOT_ACCEPTED`. Build gates and deployment identity passed; fresh-account QA on production SHA `e9c0db94671faf513f63ed21ce1783995741339a` reproduced the Automation loading state and a FINN Today card matching the deterministic DCA template; the response source was not observed. |
| Goal | Recover a first FINN Today AI briefing after a transient worker/provider failure, and prevent a slow onboarding-status refresh from blanking Automation on route transitions. |
| Candidate branch | `codex/first-briefing-automation-fix`, merged to `main` in `ced224a3c5f04d07345c1e27125eff2019f0ad3b`. |
| Candidate implementation SHA | `2a565e8a2f8a7da53ed70b7848e9d92fe7b45b16`. |
| PR | [#102](https://github.com/gvangalen/antigravity-trading-tool/pull/102), merged. |
| Production SHA | `ced224a3c5f04d07345c1e27125eff2019f0ad3b`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `8e150bdfa63202244d8702688dfa32715be3cae7`, independently tested on a fresh QA account. |
| Last updated | 2026-10-07 |

Independent QA confirmed that the DCA onboarding data, Paper bot and 4/4 completion persisted on the previous live SHA. The first FINN Today card stayed on deterministic fallback copy after refresh and relogin; the exact live `response_source` and `last_error_code` were not captured. Automation also showed a dark spinner for more than 20 seconds on first transition. These are QA observations, not a proven production worker trace.

Code investigation found three concrete retry defects: the separate retry scheduler could mark a job `retry_scheduled` before its enqueue task skipped it as already in flight; the dashboard stopped polling while fallback waited for a retry; and the shared OpenAI client allowed only one scheduled call per hour, independently of the briefing service's former second limiter. The repair uses one version-scoped client limiter with three bounded attempts and one queue path for due retries. In an isolated local PostgreSQL/Redis/FastAPI/Celery runtime, a previously stuck `retry_scheduled` record with `ai_rate_limited` advanced to `queued` and then `ready` with `response_source=ai_generated` on worker attempt two. A second controlled worker probe pre-consumed a call slot in the same hour and still reached `ready` on attempt two. Mission Control read it back as `cached_ai`. A direct synthetic Saturday-DCA prompt to `gpt-6-luna` with reasoning `none` returned a valid Dutch briefing. The exact cause of the QA account's production fallback remains unproven without its trace.

The Automation spinner is rendered by `AuthGuard` while it awaits `/api/onboarding/status` at each protected route transition. A recent user-scoped status or a verified completed account now permits the current page to render while the authoritative server check continues; stale in-flight checks cannot redirect a later navigation. Independent browser QA must verify the effect on the first Automation transition.

Local backend tests: **3169 passed, 3 skipped**; `.local-finn-parity-artifacts/first-briefing-retry-pytest-final.log` SHA-256 `8f4f54d48258f96ff086d192ba61e0b983b8c4f9758683057ec079fca565deb0`. Focused first-dashboard and call-capacity tests passed. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, onboarding handoff tests and high-severity dependency audit passed. The final isolated prefork Celery/Responses action matrix passed **16/16**, zero broker orders and live-trading calls; `.local-finn-parity-artifacts/first-briefing-retry-action-matrix-final.json` SHA-256 `2cf58c1ea347f0f7ace67c1123a43d44990c3eb9b137d21e820de7c3d1cd9735`. Real-provider selector development passed **18/18** with no provider/schema/parse/validation/timeout failures; SHA-256 `f649fcad794a5a44a47705f9d5d090adcda807739bb45df87771291b18db11f5`. The initial concurrent action matrix was **15/16** and two host-based selector regression runs ended **108/109** and **107/109** because of provider timeouts; they are recorded as red. The final 109-case Linux-runtime regression passed **109/109**, with zero provider, schema, parse, validation or timeout failures; `.local-finn-parity-artifacts/first-briefing-retry-selector-regression-linux.json` SHA-256 `b14291ce526efbf2ca2154db7983401e55c8d9b385585d4f69edbc75c336fccb`. The host-only timeout runs remain recorded as red diagnostics; the local parity-runtime release gate is green. Candidate [CI run 37630660797](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37630660797) passed all five checks, main [CI run 37631011253](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37631011253) passed, and [Auto Deploy run 37631280500](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37631280500) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `ced224a3c5f04d07345c1e27125eff2019f0ad3b`. The subsequent independent authenticated QA did not observe an AI-generated transition and saw the Automation page disappear behind a long loading state.

## Previous Release (fresh onboarding DCA)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity checks passed; independent authenticated browser QA has not run. |
| Goal | Repair fresh-user DCA onboarding and the first FINN Today briefing: save the schedule, read the saved plan and trader context, finish the background briefing, and keep optional source failures from aborting Mission Control. |
| Candidate branch | `codex/onboarding-dca-today-context`, merged to `main` in `9e34dbda017c0c7313135c47ba3f4b651a584881`. |
| Candidate implementation SHA | `78cad90c891065bb33d71dad796a1717ebd0dc54` (together with preceding branch commit `ff79f435d67cfb1dab785e6082468d70fc24c112`). |
| PR | [#100](https://github.com/gvangalen/antigravity-trading-tool/pull/100), merged. |
| Production SHA | `9e34dbda017c0c7313135c47ba3f4b651a584881`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Last updated | 2026-10-07 |

The guided onboarding form now captures a daily, weekly, or monthly DCA
schedule and persists it with the setup; the fixed amount remains in the
linked strategy. The first FINN Today briefing is dispatched independently of
the older score/report chain. Its queued worker can claim its own task, while
Mission Control queues missing briefings without a blocking provider call.
Owner-scoped setup details, strategy amount, profile context, and optional
market context reach the briefing. Fixed DCA is described as a saved schedule,
not a discretionary entry or evidence of an executed purchase. Optional
strategy, bot, indicator, and portfolio reads use database savepoints so an
unavailable source does not invalidate the rest of the request.

Measured local evidence: root pytest **3165 passed, 3 skipped**; log SHA-256
`c14913b4fbc0ab07d5472c98f3206c676ebe254ae6a7ed32b0d5f1bb43d28793`.
Frontend build, typecheck, i18n lint/tests, command/proposal tests, and
high-severity dependency audit passed. The isolated PostgreSQL/Redis/FastAPI
and prefork Celery action matrix passed **16/16**, with zero broker orders and
zero live-trading calls; artifact SHA-256
`b6ec82c85312eb368a031df78b2e11d57287e3c6a17a55ab5f0b2136664e5d21`.
Real-provider selector development passed **18/18** (SHA-256
`85c8f15afb2b76515881bd72e358a71fb423d24402cf4176d2d2fbe9237a0869`)
and regression **109/109** (SHA-256
`a62c02d8c38bce1b89dfe39a82bdf02dda5d6cf0f1f6fd773755dbad6827b8d9`),
with zero provider, schema, parse, validation, or timeout failures. A local
fresh-account API path persisted a Friday DCA setup as weekday code `5` and a
fixed strategy. A local completed-account worker produced `ready` using
`gpt-6-luna`/`none`, with the saved DCA amount and FOMO profile preference;
Mission Control returned successfully for both tested local accounts. This is
Build evidence, not independent production QA. A one-off Automation loading
delay from the earlier browser report was not reproduced here.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37614979009)
and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37615249622)
completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37615474398)
completed success for `9e34dbda017c0c7313135c47ba3f4b651a584881`.
Public backend health and frontend build-info both returned HTTP 200 and that
SHA on 2026-10-07. Build did not access the authenticated QA fixture. QA should
complete a new-account browser path with a fixed DCA schedule, strategy and
Paper bot, then verify the first FINN Today card is personal and remains
consistent after a refresh. A repeated initial Automation loading delay, if
observed, needs a run trace; it was not reproduced in local validation.

## Previous Release (indicator source evidence)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity checks passed; authenticated runtime QA is pending. |
| Goal | Expose each indicator's real source observation moment and the distinct dated source days required by absolute-value score normalizers, without changing score or execution decisions. |
| Candidate branch | `codex/score-source-evidence`, merged to `main` in `bf453f9d44777f4099e436d29a49d06d46c15243`. |
| Candidate implementation SHA | `bce8949f94a2c476d14f1c010f498d7a4cfb8d37` |
| PR | [#98](https://github.com/gvangalen/antigravity-trading-tool/pull/98), merged. |
| Previous live SHA | `bbccff3675160a6b1414d200aff1e19fc53b6da5`, reported by the user from authenticated QA. |
| Production SHA | `bf453f9d44777f4099e436d29a49d06d46c15243`, observed on both public surfaces after Auto Deploy. This status-only update will create a later SHA; QA must bind to the current backend/frontend SHA. |
| Last updated | 2026-10-07 |

The workspace projection now carries `source_observed_at` from each measured
indicator and derives freshness from that source moment, never from the receipt
timestamp. Analyse labels `sample_size` as readings in the selected period and
shows a separate count of distinct source days for Price and Volume in the
last 30 days, and DXY, S&P 500, Gold and Oil in the last 90 days. The existing
normalizers require five such days. A missing source moment appears as not
recorded. This is read-only evidence; it does not backfill market or macro
data, invent scores, change setup matches, or trigger bot decisions.

Measured local evidence: root pytest **3160 passed, 3 skipped**; frontend build,
typecheck, i18n lint/tests, command/proposal tests and high-severity dependency
audit passed. The isolated local PostgreSQL/Redis/FastAPI/prefork Celery stack
passed the safe-action matrix **16/16**, with zero prohibited executions,
`.local-finn-parity-artifacts/score-source-evidence-action-matrix.json` SHA-256
`370c6c58b1462d0ec2302dbeb836f830ed1605e6e9ceb9a61aec0e362e4c73e7`.
The real-provider selector development run passed **18/18**, SHA-256
`23e98c9ee8c30437d5d7502caa6b8e6bdec34c1cf44d395133db1d116cdaa569`;
regression passed **109/109**, SHA-256
`6f63a8a7dffe6e21b27ae57524aeef4dcebcc121608e6969ed98b3240643fd43`,
with zero provider, schema, parse, validation or timeout failures. The new
history query also executed against isolated PostgreSQL, and a local workspace
read completed. PR #98's workflow-validation, backend-tests, security-baseline,
mobile-quality and frontend-quality checks all completed success for the
implementation SHA. [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37599829650)
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37600049169)
completed success for merge SHA `bf453f9d44777f4099e436d29a49d06d46c15243`.
Public backend health and frontend build-info both returned HTTP 200 and that
SHA on 2026-10-07. Build did not access the authenticated QA fixture.

The next independent QA pass should record the actual source moment and
historical-day count for the five BTC indicators reported on 2026-10-07. One
reading in the Day view alone does not establish whether scoring has the five
distinct historical source days it needs. A positive setup match and a
score-driven Paper decision remain unproved until complete fresh sources exist.

## Previous Release (pending-source explanation)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated browser QA passed the pending-source explanation on the deployed SHA; broader scoreflow and read-parity acceptance remain open. |
| Goal | Preserve the pending-source status of a configured but unmeasured indicator through the complete asset workspace projection. |
| Candidate branch | `codex/preserve-pending-indicator-status`, merged to `main` in `9474f30a6023871c8895784853d4d9c11d513eaf`. |
| Candidate implementation SHA | `71e4946cdf60049158ca7065a63892e611b11b15` |
| PR | [#95](https://github.com/gvangalen/antigravity-trading-tool/pull/95), merged. |
| Previous live SHA | `b514fdb10356e3632129b12626e1c1898560aa80`; authenticated QA added BTC ADX and confirmed persistence, zero measurements, null value and score, but the expanded detail still said only “Onvoldoende data”. No real provider 429 occurred. |
| Production SHA | `9b47c454c971f6c589ad3ab33d790cfe593772d1` observed on both public surfaces after the status-only Auto Deploy. Any later status update creates a new SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-07 |

The root cause was in `WorkspaceDataService._enrich_indicator_rows`: `_include_configured_rows` marked an unmeasured configured indicator `pending_refresh`, but enrichment unconditionally replaced every null-value row status with `insufficient_data`. The frontend's pending explanation therefore never received its required status. The fix preserves `pending_refresh` for those rows while keeping the value, score and category score absent. A regression test covers the final technical category payload for configured ADX with no observation. This does not claim a real production 429 or a positive setupmatch or score-driven Paper decision.

Targeted authenticated QA on `9b47c454c971f6c589ad3ab33d790cfe593772d1` configured ADX for AAPL, hard-refreshed, and observed the indicator retained with zero measurements, no value and no score. Both the row and expanded detail explained that the source would be retried on the next data refresh and that there was no score yet; no browser errors occurred. This passes the specific pending-source presentation goal. No real provider 429 occurred; a positive setupmatch and score-driven Paper decision remain untested. The separate 20 read-only parity failures below remain open. This report was supplied by the user as QA evidence; no independent artifact hash was provided for this run.

Measured local evidence: root pytest **3156 passed, 3 skipped**, `.local-finn-parity-artifacts/preserve-pending-status-pytest-final.log` SHA-256 `a5bbdfe9a26803cd90f5adb56d938f5156edc955abdcbb35f283bf321fb0bbef`; frontend build, typecheck, i18n lint/tests, command/proposal tests, pending-evidence tests and high-severity dependency audit passed, build log SHA-256 `4898f64db7993188ed0110131f904fa0fd36141aaf1847c90294e76820135abf`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/preserve-pending-status-safe-action-matrix.json` SHA-256 `ec1113e6394dccc9523fcba9b79c53c7169adfc33f271de8f20eac92b1940ead`. Real-provider selector development passed **18/18**, SHA-256 `84197429a1e60d8bb6057d222a16af922bfd2a833cb53ce0242eb07571c5edd1`; regression passed **109/109**, SHA-256 `817f5ca216ff22d1523a085a11227624e880029f9fe7f6012c79b6abbb863e61`, with zero provider, schema, parse, validation or timeout failures. An additional nonsealed parity diagnostic was **not green**: the action chain reached 16/16, but 20 read-only cases did not select the expected operation. Its final artifact is `.local-finn-parity-artifacts/preserve-pending-status-full-action-matrix-final2.json` SHA-256 `2402f95e31ed8462c4798ab8eec15cb25f3bc61699f8a02ad39a7c2c94add020`. This diagnostic remains a separate FINN read-route issue and is not counted as passing. The candidate changes no read selector or operation contract.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574093759) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574310111) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574455371) completed success for `9474f30a6023871c8895784853d4d9c11d513eaf`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-07. The [status-only PR #96](https://github.com/gvangalen/antigravity-trading-tool/pull/96) also passed [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574830533) and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574979809); both public surfaces returned HTTP 200 and `9b47c454c971f6c589ad3ab33d790cfe593772d1`. Build did not access the authenticated QA fixture. A real 429, a positive setupmatch and a score-driven Paper decision remain unproved.

## Previous Release (pending explanation)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; independent authenticated QA is pending. |
| Goal | Show the persisted pending-source explanation for an indicator with no reading after a hard refresh in Analyse. |
| Candidate branch | `codex/technical-pending-evidence`, merged to `main` in `24f7959d8d5925b6d69d452881aec963cfbda642`. |
| Candidate implementation SHA | `7a63c85771fb50d35c48290eea648768513b258e` |
| PR | [#93](https://github.com/gvangalen/antigravity-trading-tool/pull/93), merged. |
| Previous live SHA | `8a8a061e8c7285322f66dbe54d28bfe9392b2b46`; targeted live QA confirmed MA 200 remains configured with zero readings and no score after refresh, but saw only generic insufficient-data text. No real provider 429 occurred in that run. |
| Production SHA | `24f7959d8d5925b6d69d452881aec963cfbda642` observed on public backend and frontend after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The Analyse workspace already receives `data_status: pending_refresh` for configured indicators without a reading. The row renderer previously collapsed that status to a generic insufficient-data detail. This change keeps score and value absent while explaining that the source will be read again on a later data refresh. It does not claim that an observed 429 caused every pending row. The scheduled configured-source sync remains responsible for retrying the read; a browser refresh alone does not create a measurement.

Measured local evidence: root pytest **3155 passed, 3 skipped**, `.local-finn-parity-artifacts/technical-pending-copy-pytest.log` SHA-256 `70256762dc7a18ef88ba6c4ac4c3851c2103aa92aad5de4e185078557408728b`; frontend build, typecheck, i18n lint/tests, command/proposal tests, pending-evidence tests and high-severity dependency audit passed, `.local-finn-parity-artifacts/technical-pending-copy-frontend-build.log` SHA-256 `b16d04531c984824cfffee9ee28091d96cb18eef3b8b9937b51ab2040b94697f`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/technical-pending-copy-full-action-matrix.json` SHA-256 `d1c9507e33b4999815bfb557b96bb7e2cf81950797bebe2f3bc4424e9a1b00f7`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/technical-pending-copy-selector-development.json` SHA-256 `4b068867a37c49496b7c7a398da919fb5fbde854112f4f5458d91240350856f3`; regression passed **109/109**, `.local-finn-parity-artifacts/technical-pending-copy-selector-regression.json` SHA-256 `00f4779b93ef947510a8f54ae88f70f8afe0f8469089339c7bbf3a475e3e6a90`. Both had zero provider, schema, parse, validation or timeout failures. This does not prove an actual production 429, a positive setupmatch with complete fresh sources, or a score-driven Paper decision.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37522979863) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37523303510) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37523609123) completed success for `24f7959d8d5925b6d69d452881aec963cfbda642`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. QA should check that an unmeasured configured indicator shows the pending-source explanation after refresh and, if a genuine provider 429 occurs, that the pending route remains usable. A positive setupmatch and score-driven Paper decision still require complete fresh sources.

## Previous Release (technical source limit)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated QA confirmed MA 200 configuration persistence and honest null score on `8a8a061e8c7285322f66dbe54d28bfe9392b2b46`, but did not encounter a real 429; the persisted pending explanation was missing. Positive-match and Paper-decision acceptance remain open. |
| Goal | Keep owner-scoped MA 200 configuration pending without a fabricated reading when its technical source rate-limits; replace the 429→500 generic failure with an explicit pending-source response and UI message. |
| Candidate branch | Merged to `main` in `ff038fbed0987bb69acb97e456352589b8a47a89`. |
| Candidate implementation SHA | `487eba47c0e7462fb1f94b6aa110e547e2bb790d` |
| PR | [#91](https://github.com/gvangalen/antigravity-trading-tool/pull/91), merged. |
| Previous live SHA | `78d3d873fae8328b29ae6c10c267e85e33a64edc`, targeted live QA passed curve/weight persistence, duplicate Price validation and FINN emphasis, but MA 200 hit provider HTTP 429 and the app returned HTTP 500. |
| Production SHA | `ff038fbed0987bb69acb97e456352589b8a47a89` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

This batch classifies Twelve Data and Binance technical HTTP 429 responses as temporary source limits. A user-triggered indicator addition persists its owner-scoped configuration with `value: null` and `score: null`; Analyse already projects configured technical indicators without readings as pending rows. A scheduled refresh still counts a rate-limited read as failed. The API commits the pending configuration and the frontend states that no score exists yet. It neither retries a rate-limited provider immediately nor invents a reading.

Measured local evidence: root pytest **3155 passed, 3 skipped**, `.local-finn-parity-artifacts/technical-rate-limit-pytest.log` SHA-256 `81b9bc1aaf4a0b203f47618eef05f0f8bbef51a00376f1293627cdbe5e8268ca`; frontend build, typecheck, i18n, commands, proposals and production high-severity audit passed, `.local-finn-parity-artifacts/technical-rate-limit-frontend-build.log` SHA-256 `26fc0866f3ef5a45fea1925ba26ade9030a08acda251cbc2cd6c9d7169416a2a`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, zero prohibited executions, `.local-finn-parity-artifacts/technical-rate-limit-full-action-matrix.json` SHA-256 `236889f1337cb0eebeaf673a918ae71781b32b61e81a6ebb40c080354b6ace4f`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/technical-rate-limit-selector-development.json` SHA-256 `5a8110a9a78922ad7a917cc2d85e6ba5a89cc22ec08257b748de61ca2295fd45`; regression passed **109/109**, `.local-finn-parity-artifacts/technical-rate-limit-selector-regression.json` SHA-256 `940defc1bf82fa8367dc95ad590f036108513ef7fcb97eee0efb72c02969fb9e`. Both runs had zero provider, schema, parse, validation or timeout failures. The 429 branches were injected in local backend tests; this is not an authenticated live test of an actual rate-limited provider. Complete fresh-source positive setupmatch and score-driven Paper execution remain unproved.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37518522551) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37518779838) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37519034762) completed success for `ff038fbed0987bb69acb97e456352589b8a47a89`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. Independent QA should verify the real provider-limit case, the persisted pending technical row after refresh, the absence of a false score/setupmatch, and the later transition to a dated value when the source recovers. The positive match and paper-bot decision need complete fresh sources.

## Previous Release (indicator score curve persistence)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated QA passed curve/weight persistence, duplicate Price validation, and FINN emphasis on `78d3d873fae8328b29ae6c10c267e85e33a64edc`; MA 200 exposed a provider 429→API 500 failure. Positive-match and Paper execution acceptance remain open. |
| Goal | Preserve custom indicator curves and weights across configuration writes, show actionable validation errors, prevent duplicate-selection side effects, and render FINN's single-star setup emphasis. |
| Candidate branch | Merged to `main` in `1e35609aacb1274f16e4eb7eb84de810356299b8`. |
| Candidate implementation SHA | `07da8518928ddcf33d3125d942267fe010aa0af6` |
| PR | [#89](https://github.com/gvangalen/antigravity-trading-tool/pull/89), merged. |
| Previous live SHA | `ee1e49ad8fc0c20d3dab685a73937fd718803140`, independently checked for the missing-data and duplicate-indicator paths. |
| Production SHA | `1e35609aacb1274f16e4eb7eb84de810356299b8` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The independent live check of the previous release found that Analyse and FINN correctly keep incomplete BTC scores and setup matches unavailable, an unscored Volume indicator persists, and a duplicate Price indicator receives a clear error. It did not inspect the raw `null` payload, retest the separate insufficient-history validation error, or prove a positive match with complete fresh sources. These remain evidence limits, not green release claims.

This batch fixes a further configuration defect found during follow-up: saving custom five-band rules and then saving settings could overwrite the rules. The frontend now submits the custom curve and weight together, and the backend preserves existing custom rules on settings updates. Adding a duplicate indicator now fails before configuration writes. The dialog surfaces 400/422 validation details and accurately reports partial creation when a later settings write fails. FINN's text renderer handles single-star emphasis around setup names.

Measured local evidence: root pytest **3149 passed, 3 skipped**, `.local-finn-parity-artifacts/indicator-score-followup-pytest.log` SHA-256 `84b5994f29c635ba83cfef6fe18dafa54aa3253776cf0af257dd3d5d9476be37`; frontend production build and typecheck passed, `.local-finn-parity-artifacts/indicator-score-followup-frontend-build.log` SHA-256 `fe6def5111edb7ed220fb20089ed08c18a44d6680ccc4a9f0cc19e55a4f3e68a`; frontend i18n, commands, proposals, focused config/chat tests and high-severity dependency audit passed, with zero reported vulnerabilities. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/indicator-score-followup-full-action-matrix.json` SHA-256 `6a5c1366911bb7e5424cc6fcd90d92fabf50ffb1ae0fe4f4e137382882431e83`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/indicator-score-followup-selector-development.json` SHA-256 `41c2e28197c422c945c6ab7036a33e84bc2cd861c4e45ee20b2780a02e74b9c3`; regression passed **109/109**, `.local-finn-parity-artifacts/indicator-score-followup-selector-regression.json` SHA-256 `671b4c8e648f12f75a5a91ff0f09012913cd5b7151612ad25aeb04085d398da4`. Both runs had zero provider, schema, parse, validation or timeout failures. A synthetic, owner-scoped positive setup-match test covers fresh and stale source evidence locally; it does not establish a live positive match or paper-bot decision with five genuinely dated observations.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513073466) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513368649) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513638120) completed success for `1e35609aacb1274f16e4eb7eb84de810356299b8`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. Independent QA should verify the raw missing-score payload, custom five-band rule/weight persistence, a visible insufficient-history error, FINN setup-name formatting, and a positive match/paper decision only with complete genuinely dated fresh sources.

## Previous Release (indicator score presentation)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Independent live QA passed the targeted missing-data and duplicate-indicator checks on `ee1e49ad8fc0c20d3dab685a73937fd718803140`; positive-match and separate validation-error acceptance remain open. |
| Goal | Repair stale and incomplete indicator-score presentation, preserve missing values in FINN evidence, and allow unscored market indicator configuration while history accumulates. |
| Candidate branch | Merged to `main` in `e7addf5459b08d39509726e21e6334624ddcefb8`. |
| Candidate implementation SHA | `d3c764cdcfa9bc2d804e5b0967c2398b13df714e` |
| PR | [#87](https://github.com/gvangalen/antigravity-trading-tool/pull/87), merged. |
| Previous live SHA | `3b2664f89b37b13fdde8d127bf1350a2c070138b`, independently tested and not accepted. |
| Production SHA | `e7addf5459b08d39509726e21e6334624ddcefb8` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The new Build batch keeps a raw indicator reading separate from a validated score. Analyse day cards and row explanations use the canonical daily score and its indicator evidence. FINN preserves missing macro and technical scores as `null` and exposes the original source timestamp. A market indicator with too little dated history can be configured but remains unscored. The config dialog now explains duplicate-indicator failures inline. These fixes do not create the missing five-observation production fixture or prove a positive match or paper execution.

Measured local evidence: root pytest **3145 passed, 3 skipped**, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-pytest.log` SHA-256 `ecd9df3e79c791764637f1be6f32a7c677204840503a751006cb51ce56f88a03`; frontend production build and typecheck passed, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-frontend-build.log` SHA-256 `0853c8d97c722f652189763c03c7c6fdade2bca2d238f1b53c06cdd7904799d3`; frontend i18n, commands, proposals and high-severity production audit passed with zero vulnerabilities. The new canonical-score presentation tests passed **2/2**. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, zero prohibited executions, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-full-action-matrix.json` SHA-256 `a8168eb0a1a93d52f1cb7e5a457a22e544d3d40358f8e93cdcd073d222aff19d`. Real-provider selector development passed **18/18**, SHA-256 `c61e11db46079b72471e615c4bac81dbcaac36bc4bcd4ec1d81873c8c003f747`; regression passed **109/109**, SHA-256 `bf414d7cdc37fceb4be4870abdbe09495221dc8fc5ae9337a7475d2d5783393a`, with zero provider, schema, parse, validation or timeout failures. Their artifacts share the `indicator-score-v2-qa-fix-selector-` prefix in `.local-finn-parity-artifacts/`.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37506880820) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37507227211) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37507564081) completed success for `e7addf5459b08d39509726e21e6334624ddcefb8`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. The next QA pass must check AAPL stale DXY and one-observation Price presentation, FINN's S&P 500 missing-score semantics, duplicate and insufficient-history indicator configuration, and a controlled positive setupmatch/paper decision only when five genuinely dated measurements per required source are available.

## Previous Release (indicator score flow v2)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; this candidate is not independently accepted. |
| Goal | Unify indicator scoring and dated benchmark evidence across FINN, Analyse, Mijn Plan, reports, mobile and bot score input. |
| Candidate branch | Merged to `main` in `56e8a255ad34b74391ec0ae28724e4eb55ddaf95`. |
| Candidate implementation SHA | `a492d7e1f660dcdf60437fe7a7756bb836757722` |
| PR | [#85](https://github.com/gvangalen/antigravity-trading-tool/pull/85), merged. |
| Previous live SHA | `cb0c24827a853c616e0145d652f5353f2e9f8d24`. |
| Production SHA | `56e8a255ad34b74391ec0ae28724e4eb55ddaf95` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The score-flow code passed local root pytest (3142 passed, 3 skipped), frontend build, mobile typecheck/lint/web smoke and migration plan validation. The frontend export was rebuilt, and the production dependency audit passed with zero vulnerabilities after updating the `sharp` override. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37498674203) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37499125577) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37499391196) completed success for `56e8a255ad34b74391ec0ae28724e4eb55ddaf95`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06.

The isolated local PostgreSQL/Redis/FastAPI/prefork Celery stack used the real Responses provider and synthetic fixture users. The worker-driven safe-action matrix passed **16/16** with zero prohibited executions: `.local-finn-parity-artifacts/indicator-score-flow-v2-full-action-matrix.json`, SHA-256 `10c048fd645a6ac49ed701f6c88b8c0a950a87bad1e0d604e3e6d0de15071d96`. Real-provider selector development passed **18/18**: `.local-finn-parity-artifacts/indicator-score-flow-v2-selector-development.json`, SHA-256 `eb416a8e6a45cb67854e4c7a425cdc497376162c65d91ac48179f2edb4ddc170`. Real-provider selector regression passed **109/109**: `.local-finn-parity-artifacts/indicator-score-flow-v2-selector-regression.json`, SHA-256 `63f984a2a1c9e045db9fa59da9cde06018ca85f4c9f476500a98ac44dc939728`. Both selector runs had zero provider, schema, parse, validation and timeout failures. The isolated migration completed successfully. Independent authenticated live QA later tested production SHA `3b2664f89b37b13fdde8d127bf1350a2c070138b` and did not accept the score flow because of stale partial scores, missing-to-zero FINN evidence and configuration errors.

## Previous Release (setup-score repair)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; this candidate is not independently accepted. |
| Goal | Repair Analyse ↔ FINN score evidence, setup-boundary reads with multiple strategies, exact Smart-DCA threshold readback, and the paper-bot `NaN` display. |
| Candidate branch | Merged to `main` in `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Candidate implementation SHA | `cece6f8ce964a3df7c29c1992ee85cf23af7b1c9` |
| PR | [#83](https://github.com/gvangalen/antigravity-trading-tool/pull/83), merged. |
| Previous live SHA | `82f8b6bec76b80234e4a8b1222aa96fb9cd5cc3b`, reported by independent live QA as not accepted. |
| Production SHA | `1f50e2f3adc682de0bf2f468be7aaddbc89e4561` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Release owner | Build |
| Last updated | 2026-10-06 |

## Change And Limits

- FINN reads the same owner-scoped saved daily market score as Analyse. It receives source status separately and does not treat a reported score as a verified complete benchmark.
- Saved setup score boundaries remain readable without choosing among linked strategies. The setup-match tool carries those conditions even when current scores are incomplete.
- Smart-DCA score bands and hypothetical amounts are derived from the execution curve engine. Exact score 70 selects the high band in a 40/70 step curve.
- The paper-bot card displays a missing stop-loss instead of `€ NaN`.
- A dated score report can be read even when it precedes today; its report date does not establish current source freshness.
- The [live test plan](../operations/setup-market-match-live-test-plan.md) includes the QA regressions. The one generic failure turn has no runtrace, so its exact cause is not established. A positive match, paper-bot decision with fresh sources, and authenticated cross-surface behavior remain for independent QA.

## Measured Local Build Evidence

All runtime artifacts below used an isolated local PostgreSQL, Redis, FastAPI and prefork Celery stack with the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`. The selector used its separately configured provider model. The local matrix made no broker orders, live bot activations, live trading calls or production connections.

| Gate | Result | Evidence |
| --- | --- | --- |
| Worker-driven safe action contracts | `16/16`; zero prohibited executions. | `.local-finn-parity-artifacts/setup-match-qa-fix-full-action-matrix.json`, SHA-256 `5fc3d48fba1815bf4e88cdb461bae9144820a7c7ae6e42673c952d6e8cdc92fd`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-match-qa-fix-selector-development.json`, SHA-256 `af7d0cf41d9597ad74ef946145575274392c2a741ac269c03537010e5db7c886`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. Selector implementation was unchanged after this run. | `.local-finn-parity-artifacts/setup-match-qa-fix-selector-regression.json`, SHA-256 `ae6dcfa79f07048bc30182d0430f829c00bf9a8aadbf71794b0fce83ac2a726d`. |
| Local Responses/API/Celery conversation | Named BTC setup bounds with two strategies, follow-up against incomplete scores, saved market score 100 with stale source, and exact Smart-DCA score 70 → €90 all completed read-only. | `.local-finn-parity-artifacts/setup-match-qa-fix-live-probe.json`, SHA-256 `cb5173f4961678f75fa8fb21d1f471d28009aa8c1d5db9bd14c4f8942099ed88`. |
| Dated saved-score conversation | Both turns completed read-only; prior score report date and three values read, no current trade signal inferred. | `.local-finn-parity-artifacts/setup-match-qa-fix-score-date.json`, SHA-256 `d3512dfd695c40765cc328f55c561019fe61ffb5f5346fcdb87dbea678a44ab7`. |
| Backend | `3133 passed, 3 skipped`; includes typed tool, source-status, setup-boundary, Smart-DCA threshold and conversation regressions. | `pytest -q --disable-warnings`; `.local-finn-parity-artifacts/setup-match-qa-fix-pytest.log`, SHA-256 `3aa5133d49c48836ff3ade3da2bae0cf49717aeed19f61f92b66929df5873bc1`. |
| Frontend | Build, typecheck, i18n lint/tests, commands, proposals, setup tests and high-severity production dependency audit passed; zero vulnerabilities. | `.local-finn-parity-artifacts/setup-match-qa-fix-frontend-build.log`, SHA-256 `7adc82013f7addf1e524a5f4cba3ae91b7da2aa70c0a0ca4bf72a4e062744d6f`. |

An additional 37-case public parity runner was tried and did not pass. Its old DCA setup prompt lacks the now-required amount, so clarification is correct, while its read probes require legacy operation IDs absent from the current model-led chat route. This runner is not the required 16-action contract gate; its mismatch is recorded rather than counted as green.

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | [PR #83 CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37420681594) completed success. |
| Main CI and Auto Deploy | [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37420888542) and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37421015126) completed success for `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Public backend health and frontend build-info | On 2026-10-06 both returned HTTP 200 and SHA `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Independent authenticated live QA | Pending for this candidate; only QA owns the fixture and verdict. |
