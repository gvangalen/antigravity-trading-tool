# FINN `19e044c` QA root-cause matrix

Source evidence: independent production report and raw `canary.json`,
`development.json`, `regression.json`, `sealed-holdout.json`, `runtime.json`,
and `runtime-summary.json` in `/private/tmp/finn-19e044c-results`.

| QA family | First failing boundary | Production evidence | Why prior Build tests passed | Candidate repair and proof |
| --- | --- | --- | --- | --- |
| Natural setup vs plan | Structured selector manifest | Litecoin setup wording selected `read_active_plan`; entity stayed `Litecoin`. | Existing cases used literal `setup` wording and mocked structured output. | Clarify generic setup/plan descriptions; canonicalize `Litecoin→LTC`; published prompt plus distinct setup variant are regression cases. |
| Evaluation vs mutation | Structured selector manifest | “minst overtuigend onderbouwde schakel” selected `clarify_request` with update polarity. | Contract tests asserted known evaluation phrasing rather than the model boundary for audit language. | State explicitly that assess/audit/least-supported language is read-only `evaluate_plan`; two generic evaluation regressions. |
| Natural asset normalization | Preprocessor/catalog boundary | `watchlist_remove` was correct but `dogecoin` escaped as entity and target. | Tests covered Cardano/Avalanche only; no shared canonical DOGE record existed. | Add DOGE and LTC to canonical catalog before selector/state/proposal identity; published and variant regression cases. |
| Personal indicators and stale workspace | Response adapter before verifier | Correct asset-scoped tools/evidence ran but terminal response was rejected for missing `configured_count` and `indicator_names`. | Deterministic fallback tests passed, but model-backed runtime drafts bypassed that fallback and the final serialized draft was not tested. | Project contract-required evidence facts into the draft before verifier/persistence; verifier coverage regressions assert the terminal draft fields. |
| Bot status | Response adapter before verifier | Five bot-chain reads completed then downgraded for missing `bot`/`bot_status`. | Graph coverage unit used a hand-written complete draft, not a model-shaped incomplete one. | Same pre-verifier contract projection emits linked bot identity plus exact live/not-live status. |
| EVALUATE and lineage | Reasoning repair fallback | Unsafe model claim led to evidence limitation, `schema_invalid`, no verified context, then evidence/reformulation/bot follow-ups became unavailable. | Unit fixture asserted a safe fallback object but did not require it to remain a useful EVALUATE delivery with durable lineage. | Evidence-limited fallback keeps `EVALUATE`, factual evidence refs and a direct least-supported evidence-gap answer; causality guard remains strict. |
| Off-topic recovery | Consequence of missing verified context | Weather did not overwrite context, but no prior verified EVALUATE existed to recover. | Isolation was tested independently from a persisted grounded EVALUATE chain. | Runtime fixture must prove persisted `last_verified_context` from EVALUATE, retention across off-topic, and terminal polling/SSE follow-up delivery. |

## Invariants retained

- No keyword or V1 operation router.
- No relaxation of `unsupported_configuration_causality`, ownership, tool, proposal or live-bot safety controls.
- Proposals remain confirmation-gated and idempotency remains canonical-contract based.
