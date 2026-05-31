# FINN 2.0 QA Release Gate

This gate is the final production-readiness layer for the FINN 2.0 test-pass roadmap.

## Purpose

We want a repeatable answer to a simple question:

> If we replay the same QA-style prompts that previously broke FINN, does the current release behave like a trustworthy read-first assistant?

## Assets

- Promptset: [finn-qa-promptset-full.json](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json)
- Replay script: [run_finn_qa_replay.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_finn_qa_replay.py)

## What the gate checks

The gate replays:

- general help prompts
- education prompts
- explain prompts
- coaching prompts
- product-help prompts
- one transactional setup prompt
- a mixed multi-turn stress mini-sequence

For each prompt it records:

- HTTP status
- detected intent
- selected flow
- `analysis.mode`
- `analysis.route_source`
- `analysis.context_confidence`
- latency
- latency bucket
- whether the answer looks like a generic failure
- whether the answer drifted into a forbidden transactional flow
- whether a failure looks like `product_quality` or `operational_qa_path`

## Pass Criteria

The release gate is green only if all of these hold:

1. `no_generic_failures = true`
2. `no_transactional_misroutes = true`
3. `stable_mixed_session = true`
4. `chat_latency_budget_ok = true`
5. `mission_control_latency_budget_ok = true`
6. no individual prompt case fails its intent / mode / forbidden-flow checks

## Usage

Set a bearer token in the environment:

```bash
export FINN_QA_BEARER_TOKEN="<token>"
```

Run the replay:

```bash
python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_finn_qa_replay.py \
  --base-url https://tradamind.com \
  --promptset /Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json \
  --output-json /tmp/finn-qa-report.json \
  --output-md /tmp/finn-qa-report.md \
  --delay-seconds 2.5 \
  --strict
```

`--strict` exits non-zero when the release gate fails.
Use `--no-delay` only for explicit stress-only runs where you want to measure burst behavior instead of stable QA pacing.

For a normal web-login flow, you can also replay with cookies instead of a bearer token:

```bash
export FINN_QA_PASSWORD="<password>"

python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_finn_qa_replay.py \
  --base-url https://tradamind.com \
  --promptset /Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json \
  --login-email "<email>" \
  --password-env FINN_QA_PASSWORD \
  --output-json /tmp/finn-qa-report.json \
  --output-md /tmp/finn-qa-report.md \
  --delay-seconds 2.5 \
  --strict
```

If the local machine has a broken CA bundle for this environment, append `--insecure`.

## Notes

- The gate is deliberately focused on front-door quality, not deep exchange-side execution.
- It is acceptable for explain prompts to return low-confidence answers when context is weak.
- It is not acceptable for explain/help/coaching prompts to route into `bot_creation`, `strategy_creation`, `setup_creation`, or `indicator_config`.
- Failures should be read in two buckets:
  - `product_quality`: FINN chose the wrong lane, generic-failed, or answered the wrong thing.
  - `operational_qa_path`: auth, timeout, rate-limit, or other runtime-path instability interfered with clean measurement.
