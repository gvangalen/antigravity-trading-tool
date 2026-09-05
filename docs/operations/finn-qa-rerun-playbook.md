# FINN QA Rerun Playbook

Last updated: 2026-05-30

## Goal

Run a clean FINN quality rerun without getting blocked by:

- unstable interactive login
- stale session/draft carry-over
- manual prompt drift
- missing replay artifacts

This playbook is intentionally small and operational.

Use the preflight first:

- [FINN QA Preflight Checklist](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-preflight-checklist.md)

## Preconditions

Before running a full rerun, confirm:

1. external smoke is healthy
   - `/api/health` -> `200`
   - `/api/system/health` -> `401`
   - `/report` -> `200`
2. the canonical QA fixture is configured according to
   [FINN QA Fixture Contract](finn-qa-fixture-contract.md)
3. you use a fresh token or fresh cookie-login
4. you avoid reusing an old browser assistant session unless that is the thing you are explicitly testing

## Recommended QA Auth Route

### Preferred: issue a QA bearer token

Use the bounded server-side flow in
[FINN Authenticated Runtime Gate](finn-authenticated-runtime-gate.md). It mints
for `FINN_QA_USER_ID` and keeps the token in process memory; never export it to
a workstation or print the helper output.

Why this is preferred:

- no dependence on flaky interactive login
- no cookie/browser uncertainty
- deterministic identity and token handling for FINN replay runs

### Fallback: cookie-based login

Use this only when you explicitly want to validate the web login path too.

```bash
export FINN_QA_PASSWORD="<password>"

python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_finn_qa_replay.py \
  --base-url https://tradamind.com \
  --promptset /Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json \
  --login-email "henk@example.com" \
  --password-env FINN_QA_PASSWORD \
  --delay-seconds 2.6 \
  --strict
```

## Release-Gate Replay

Preferred run:

```bash
python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_finn_qa_replay.py \
  --base-url https://tradamind.com \
  --promptset /Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json \
  --output-json /tmp/finn-qa-report.json \
  --output-md /tmp/finn-qa-report.md \
  --delay-seconds 2.6 \
  --strict \
  --insecure
```

Notes:

- `--delay-seconds 2.6` reduces false negatives from chat rate limiting during replay.
- `--insecure` is only for environments where the local CA bundle does not trust the server certificate chain.

## After The Replay

Read the JSON/Markdown report and classify the result:

### Green enough for full QA rerun

- no generic failures
- no transactional misroutes
- mixed session is stable
- remaining issues, if any, are narrow and understandable

Then let the QA agent rerun the full product evaluation.

### Not green yet

Split findings into:

1. **FINN content/routing issue**
   - wrong intent
   - wrong flow
   - weak context answer
   - wrong explain-vs-build behavior

2. **Operational QA-path issue**
   - rate limit
   - timeout
   - auth instability
   - startup/runtime wobble

Do not treat category 2 as a product-quality win or loss without saying so clearly.

## Suggested Execution Order

1. external smoke
2. issue fresh QA token
3. run release-gate replay
4. inspect failures
5. if replay is green enough, run the full QA agent audit
6. compare against the previous complete baseline

## Baseline Reminder

Until a fully clean second complete run exists, the previous valid full FINN report remains the best reference baseline.
