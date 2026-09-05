# FINN QA Preflight Checklist

Last updated: 2026-05-31

## Goal

Decide whether a FINN QA run is valid before spending time on:

- replay gate runs
- full 49-case live evaluations
- score comparisons against earlier baselines

This checklist exists to stop us from scoring the wrong release, scoring against a half-healthy backend, or treating a health-only pass as a valid FINN run.

## Rule

Do **not** run the full FINN QA evaluation unless every preflight section below is green.

If one section fails, stop there and classify it as a:

- runtime/deploy issue
- auth issue
- chat-path issue
- FINN quality issue

## 1. Release Identity

Confirm the exact live commit first.

Required checks:

1. host `HEAD` matches the commit we intend to test
2. PM2 backend is running from the expected backend cwd
3. we explicitly record the tested commit in the QA notes

Minimum evidence to capture:

- `host HEAD = <commit>`
- PM2 backend `exec cwd`

If the live commit is not the intended one:

- do not run QA
- fix deploy/version drift first

## 2. Runtime Health

Health must be green both internally and externally.

Required checks:

1. internal backend health
   - `http://127.0.0.1:8000/api/health` -> `200`
2. external backend health
   - `https://tradamind.com/api/health` -> `200`
3. public report route
   - `https://tradamind.com/report` -> `200`

Important:

- internal `200` alone is not enough
- external `200` alone is not enough
- both must be green at the same time

If internal is green but external is not:

- classify as nginx/frontdoor/runtime issue
- do not run QA yet

## 3. Auth Preflight

Use the canonical fixture and a fresh QA bearer token whenever possible. See
[FINN QA Fixture Contract](finn-qa-fixture-contract.md) and
[FINN Authenticated Runtime Gate](finn-authenticated-runtime-gate.md).

Required checks:

1. mint a fresh token
2. confirm token generation succeeded
3. use that token for the next probe immediately

Preferred auth route:

Issue a token only server-side, with the configured `FINN_QA_USER_ID`, through
the canonical fixture contract. Do not put the token or fixture identity in a
terminal transcript or artifact.

Fallback route:

- mint directly on the server only when the helper path is blocked

If token creation is flaky:

- classify as auth-path issue
- do not trust a full QA run yet

## 4. Tokenized Chat Probe

This is the most important preflight after health.

Required check:

- one authenticated `POST /api/assistant/chat` request returns `200`
- it completes in normal time
- it does not timeout

Recommended probe:

- `Hoi FINN, wat kun je voor mij doen?`

Pass criteria:

- HTTP `200`
- non-empty FINN response
- no `500`
- no `read timeout`

If this probe fails:

- do not run replay gate
- do not run the full QA evaluation
- classify it as a chat-path/runtime issue, not a FINN score

## 5. Mini FINN Probe Set

Before replay, run three small prompt probes to confirm the major read-only families are alive.

Recommended probes:

1. general help
   - `Hoi FINN, wat kun je voor mij doen?`
2. education
   - `Wat is RSI in simpele taal?`
3. context explain
   - `Welke strategie bekijk ik nu?`

These should confirm:

- correct intent family
- reasonable latency
- no generic fallback failure

If one of these fails:

- fix that family first
- do not move on to full replay

## 6. Replay Gate

Only after sections 1 through 5 are green.

Required result:

- replay gate completes
- no generic failures
- no transactional misroutes
- mixed session stable
- latency budgets acceptable

If replay gate is not green:

- classify the failure as either:
  - product quality
  - operational QA path

Do not claim a new full QA score from a broken replay state.

## 7. Full QA Evaluation

Only after replay gate is green.

Then, and only then:

1. run the complete 49-case evaluation
2. compare to previous valid baselines
3. record:
   - commit
   - health status
   - auth status
   - replay result
   - full score

## Required Run Header

Every future QA note should start with this header:

```text
live commit:
internal health:
external health:
report route:
auth token:
tokenized chat probe:
mini FINN probes:
replay gate:
full QA score:
```

If any line above is missing, the run is incomplete.

## Decision Table

### Safe to score

You may treat the run as a valid FINN measurement only when:

- live commit is confirmed
- internal health is `200`
- external health is `200`
- tokenized chat probe is `200`
- replay gate is green

### Not safe to score

Do **not** treat the run as a valid FINN score when:

- release commit is unclear
- health is only partially green
- tokenized chat probe times out
- replay gate is failing because of runtime/auth noise

## Why this checklist exists

We repeatedly saw confusion from three different states being mixed together:

- app health was green
- but the wrong commit was live
- or chat/auth/runtime was not stable enough for QA

This checklist forces those apart so we stop debating invalid runs after the fact.
