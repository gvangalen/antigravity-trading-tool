# FINN QA repair build report

Candidate branch: `codex/finn-qa-a290-repair`

Candidate code revision: `5b7a539b61a0ffeb5a5d501c748f23234cc104c7`

This Build report repairs the QA findings against `a29089dfcb319c28727b9ba118302527f01aa3c0`.
No production deployment was performed.

## Scope completed

- Canonical explicit-target resolution now flows from selected contract to tool planning.
- Selector facts retain typed entities, target asset, polarity, conversation reference, and missing inputs.
- Contract semantics distinguish personal reads, evaluation, explanation, unsupported financial requests, off-topic requests, and guided writes.
- Identified create targets select their typed create contract while incomplete contract slots remain explicit `missing_inputs`.
- Watchlist, plan, bot safety, evidence-follow-up, reformulation, and guided-operation boundaries have regression coverage.
- SSE payload serialization uses the same JSON-safe representation as polling.
- Release metadata no longer advances `LAST_GOOD_COMMIT` solely from a deploy attempt.

## Provider boundary

The direct real-provider RSI canary passed on the candidate code:

- provider status: `completed` (HTTP 200)
- structured parse: passed
- validation: passed
- operation: `explain_financial_concept`
- entity concept: `RSI`
- fallback: none

## Real-model evals

All runs called the direct structured selector with the configured real provider. Provider response bodies and identifiers are intentionally not stored in this report.

| Dataset | Runs | Cases/run | Operation | Entities | Target asset | Polarity | Conversation ref | Clarification | Missing inputs | Provider/schema/parse/validation/timeout failures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development | 3 | 29 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% / 0% / 0% / 0% / 0% |
| regression | 3 | 23 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% / 0% / 0% / 0% / 0% |

Development latency (p50/p95 ms): `1761/3183`, `1896/4292`, `1663/3543`.

Regression latency (p50/p95 ms): `1597/2030`, `1594/2914`, `1581/2598`.

Final regression confusion matrix has only diagonal selections:

```text
activate_bot 1, capability 1, clarify_request 1, create_setup 2,
evaluate_indicator_configuration 1, evaluate_plan 2,
explain_financial_concept 1, explain_previous_evidence 1, off_topic 1,
read_active_asset 2, read_active_plan 1, read_active_setup 1,
read_indicator_configuration 2, reformulate_previous_response 1,
unsupported_financial_operation 2, watchlist_add 1, watchlist_remove 2.
```

The prior QA holdout material was converted only to named regression coverage where it was no longer independent. No new sealed holdout was executed or used for tuning.

## Local verification

- `pytest -q`: `1440 passed, 2 skipped`
- `pytest -q backend/trading-tool-backend/backend/tests/test_finn_v2_*.py`: `503 passed, 2 skipped`
- frontend `npm run typecheck`: passed
- frontend `npm run lint:i18n`: passed
- frontend `npm run test:i18n`: `7 passed`
- frontend `npm run test:commands`: `5 passed`
- frontend `npm run build`: passed
- `git diff --check`: passed

## Handoff

This candidate is ready for independent QA. The remaining acceptance decision, including fresh sealed holdout and authenticated stateful production validation, belongs to QA and was not substituted by Build.
