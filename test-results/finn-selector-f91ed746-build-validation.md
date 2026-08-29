# FINN repair Build validation: f91ed746

This is Build evidence only. It is not an independent QA acceptance and this
branch was not deployed.

## Local validation

- `pytest -q`: `1469 passed, 2 skipped`.
- Registry validation: `validated_cases=86`.
- `git diff --check`, `bash -n` for deploy and rollback scripts, and
  `node --check ops/deploy/ecosystem.shared.js`: passed.

## Direct real-provider boundary

An isolated remote checkout of this branch inherited the configured backend
process environment without modifying the production checkout or calling a
FINN runtime route.

- RSI canary: HTTP provider status `completed`, strict parsed output present,
  `explain_financial_concept`, concept `RSI`, no selector error.
- Development direct samples: 3/3 operation, entity, target, action,
  conversation-reference, clarification, missing-input, parse and validation
  matches; provider/schema/timeout failures 0%. p50 latency 1793 ms.
- Regression direct samples: 3/3 on the same metrics; provider/schema/timeout
  failures 0%. p50 latency 1411 ms.

The command accidentally evaluated the full fixture lists before slicing its
in-memory sample report because the list comprehension was sliced after
evaluation. It created no conversations, tools, proposals, writes or
executions. This report intentionally does not claim a formal full-dataset
result from the discarded rows; independent QA remains responsible for the
release gate and may run its own frozen datasets.
