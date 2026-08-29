# FINN selector a6bca13 repair Build report

Source release: `a6bca13bae934a15abeff3fd99ea873bbaf9a7a2`.

Candidate SHA: the commit containing this report on branch
`codex/finn-a6bca13-qa-repair`.

No production deployment was performed. No sealed holdout was created, run,
changed, or used for tuning.

## Source and repairs

- Root-cause matrix: `test-results/finn-selector-a6bca13-root-cause-matrix.md`.
- The requested `finn-selector-a6bca13-final-qa-report.md` source filename was
  unavailable; the corresponding independent production report available to
  Build was `finn-selector-b13b871-final-qa-report.md`.
- Added canonical `Avalanche -> AVAX` catalog resolution before typed selector,
  target and proposal processing.
- Replaced transient run/draft proposal identity with a canonical
  operation/target/change key. Equivalent active drafts are reused across
  distinct runs while source provenance and full payload hashes remain intact
  for confirmation and execution revalidation.
- Promoted every previously published sealed QA case that was not already
  present into fixed regression coverage, then added semantic variants for
  capability, active setup, elliptical reformulation and Avalanche.

## Direct provider canary

`Wat betekent RSI?` was run through the isolated real OpenAI structured
selector. Provider status was `completed` (HTTP 200); strict parse and
validation passed; operation was `explain_financial_concept`; concept was
`RSI`; no fallback occurred.

## Real-model selector measurements

All six runs used the configured real provider directly from an isolated
candidate copy. Each result had 0% provider, schema, timeout, parse and
validation failures.

| Dataset/run | Cases | Operation | Entities | Target | Polarity | Conversation ref | Required inputs | p50/p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| development 1 | 18 | 100% | 100% | 100% | 100% | 100% | 100% | 1363/1855 |
| development 2 | 18 | 100% | 100% | 100% | 100% | 100% | 100% | 1282.5/1990 |
| development 3 | 18 | 100% | 100% | 100% | 100% | 100% | 100% | 1334.5/2501 |
| regression 1 | 46 | 100% | 100% | 100% | 100% | 100% | 100% | 1326.5/1852 |
| regression 2 | 46 | 100% | 100% | 100% | 100% | 100% | 100% | 1342.5/2299 |
| regression 3 | 46 | 100% | 100% | 100% | 100% | 100% | 100% | 1450.5/2201 |

All six confusion matrices were diagonal. The final 46-case regression matrix
contained: activate bot 3, capability 3, clarification 3, create setup 4,
evaluate indicators 1, evaluate plan 3, explain concept 2, explain evidence
2, off-topic 2, active asset 3, active plan 2, active setup 3, indicator read
3, reformulation 3, unsupported 3, watchlist add 3 and watchlist remove 3.

## Runtime and local validation

- FINN V2: `516 passed, 2 skipped`
- Full backend: `1453 passed, 2 skipped`
- Proposal cross-run canonical-draft reuse regression: passed
- Existing proposal/confirmation/execution/idempotency, safety, account and
  target-isolation coverage: included in the green FINN V2 and full backend
  suites.
- Existing polling/SSE transport parity, evidence, verifier and lineage
  coverage: included in the green FINN V2 and full backend suites.
- Frontend `npm run typecheck`: passed
- Frontend `npm run lint:i18n`: passed
- Frontend `npm run test:i18n`: `7 passed`
- Frontend `npm run test:commands`: `5 passed`
- Frontend `npm run build`: passed
- Frontend `npm run audit:high`: `0 vulnerabilities`
- `git diff --check`: passed

## Handoff

The candidate is ready for a new independent QA round. Build has not claimed
production acceptance and has not deployed it.
