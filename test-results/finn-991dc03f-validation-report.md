# FINN 991dc03f QA Repair Validation Report

Candidate source SHA at validation: `fae0ee33739096bcdc898290246bffd0f0decf62`.

## Local Validation

| Gate | Result |
| --- | --- |
| Full backend suite | `1508 passed, 2 skipped` |
| FINN lifecycle, dispatch, polling/SSE and reliability subset | `84 passed` |
| Setup, registry, target and classification subset | `109 passed` |
| Eval registry | `90` validated cases |
| Frontend typecheck, i18n, command tests, high audit and production build | passed |
| `git diff --check` | passed |

## Direct Structured Provider

All calls used the isolated server-side checkout at the candidate source SHA,
the configured OpenAI provider, and the direct selector only. No FINN chat
route, tools, proposals, confirmation, execution, or business write ran.

| Dataset | Cases | Operation/entities/target/polarity/reference/clarification/missing inputs | Provider/schema/parse/validation/timeout failures | p50 | p95 |
| --- | ---: | --- | --- | ---: | ---: |
| development | 18/18 | 100% | 0% | 1692.5 ms | 3199 ms |
| regression | 56/56 | 100% | 0% | 1576.5 ms | 3592 ms |

The RSI canary completed with `explain_financial_concept`, concept `RSI`, and
parsed structured output. Targeted completed calls included:

| Scenario | Response ID | Latency |
| --- | --- | ---: |
| RSI concept | `resp_0c2f35e068459fe0006a93fa0aab1487d1a69712c40110c68e` | 1616 ms |
| BTC plan evaluation | `resp_02a5a211e32994be006a93fa13b6a487d186640e236ff929ea` | 1312 ms |
| SOL position setup | `resp_01494b5e80ed19f6006a93fa1253f087d1a4892f25457b98bb` | 1394 ms |
| Degraded evidence follow-up | `resp_02e48ad22d4c91f7006a93fa15363087d1b5d77a6f3c760954` | 1626 ms |
| Degraded reformulation | `resp_0f6314795ec8aaa1006a93fa16ae1c87d180fb9db670c59f95` | 1879 ms |
| Degraded bot follow-up | `resp_0298a854ec6db9eb006a93fa18892c87d183f23283ee6d0d79` | 1459 ms |

Each listed provider call completed and passed structured parse and contract
validation. The isolated checkout has no local PostgreSQL credentials for
usage telemetry, and its telemetry write errors were fail-open; the completed
provider result and selector validation were unaffected.

## Operations Invariants

No deployment ran. The production checkout remains
`991dc03f09965def8d612cd5e86953a3481c56a4`; canonical
`/home/ubuntu/ops/deploy/LAST_GOOD_COMMIT` remains `48fb8721`.

The historical instruction references `107/107` selector results, but the
authoritative current `991dc03f` tree contains 90 versioned selector cases
(18 development, 56 regression, 16 sealed holdout) and no 107-case source or
the named final QA-report artifact. The candidate validates every current
non-sealed case with the real provider; no sealed holdout was created or rerun.
