# FINN selector b13b871 QA repair candidate

## Scope

- Source release: `b13b871087786a9e79fc6b1d519e3df19242a0b7`
- Candidate branch: `codex/finn-b13-qa-repair`
- Production deployment: **not performed**
- Sealed holdout: **not executed or modified**
- Root-cause matrix: `test-results/finn-selector-b13b871-repair-root-cause-matrix.md`

## Structural repairs

- Typed bot activation now distinguishes live execution from bot reads, configuration and unsupported autonomous management, while retaining the high-risk safety contract.
- Guided `create_setup` persists its operation, target and accumulated typed slots; incomplete starts remain in the guided operation and complete inputs produce one draft proposal.
- Verified financial lineage is preserved across evidence, reformulation and bot-implication follow-ups. Off-topic, unavailable, conceptual and proposal turns cannot overwrite the last grounded basis.
- General indicator education remains separate from personal indicator reads. Explicit zero-configuration evidence can produce a truthful verified response without invented records.
- Operation, entities, target, polarity, missing inputs and lineage are projected from the typed model contract instead of being rejected or overwritten by a shadow vocabulary router.
- Published QA failures were added to regression; the sealed holdout fixture was unchanged.

## Real provider validation

Direct RSI canary on the isolated candidate copy used `gpt-4o-mini` and returned provider status `completed`, parsed output, `explain_financial_concept`, and canonical concept `RSI`.

| Dataset/run | Cases | Operation | Entity | Target | Polarity | Conversation ref | Required inputs | Off-topic | Unsupported | Infrastructure failures | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development 1 | 18 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 1335.5 | 1898 |
| development 2 | 18 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 1314 | 3425 |
| development 3 | 18 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 1287 | 1792 |
| regression 1 | 30 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 1465.5 | 3326 |
| regression 2 | 30 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 1363 | 1694 |
| regression 3 | 30 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 1433 | 2232 |

All six confusion matrices are fully diagonal. Provider, schema, parse, validation and timeout failure rates are each `0%`; retry count is zero for every case. Raw case results, response IDs, latencies, attempts and confusion matrices are stored under `test-results/finn-selector-b13b871-real-provider/`.

## Runtime and safety validation

- Selector/registry/request/eval targeted slices: green.
- Live-bot polarity, guided setup, plan/evidence/reformulation/bot lineage and personal/general RSI regressions: green.
- Proposal, confirmation, execution, idempotency, account/target isolation and live-action safety: `34 passed`.
- Delivery transport parity, coverage, evidence integrity, claim grounding and lineage: `21 passed`.
- FINN V2 suite: `514 passed, 2 skipped`.
- Full backend: `1451 passed, 2 skipped`.
- Frontend: typecheck green; i18n `7 passed`; commands `5 passed`; production build green; `audit:high` found `0` vulnerabilities.
- `git diff --check`: green.

The skipped backend cases are pre-existing environment-dependent tests. No verifier, confirmation, execution or live-bot safety condition was relaxed.

## Candidate verdict

**READY FOR INDEPENDENT QA.** The Build acceptance thresholds are met on three separate development and regression runs. This report does not claim production acceptance; no deployment or new sealed holdout was performed.
