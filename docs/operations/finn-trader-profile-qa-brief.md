# FINN Trader Profile QA Brief

Last updated: 2026-06-23

## Purpose

This brief is for the QA agent that validates the completed FINN trader-profile rollout.

The goal is not broad exploratory QA.
The goal is to answer one release question:

> Does FINN now use the trader profile consistently, credibly, and safely across the main product flows?

This pass should produce:

- a release-quality score for profile-aware FINN behavior
- clear findings on consistency, coaching quality, and governance safety
- a short go / caution / block recommendation

## Release Under Test

Do not use a stale hardcoded commit here.

The QA agent must record the actual intended release commit that is live at test start.

Use this rule:

- if staging was explicitly deployed for this QA pass, record that deployed commit
- if staging was not freshly redeployed, record the confirmed live commit from the host and treat that as the release under test
- if the brief and the live host disagree, update the QA note to the confirmed live commit before scoring

Current staging truth from the latest preflight:

- confirmed live staging commit: `df4e308`

Record this at the top of the QA output:

```text
branch: codex/finn-product-sprint1-staging-candidate
commit: <confirmed live commit at test start>
feature scope: FINN trader profile rollout tranches 1-4
```

Example for the current staging environment if unchanged:

```text
branch: codex/finn-product-sprint1-staging-candidate
commit: df4e308
feature scope: FINN trader profile rollout tranches 1-4
```

Latest fully valid staging certification reference:

- commit: `df4e308`
- weighted score: `91.5/100`
- verdict: `go`

## Required Preflight

Do not score the release until these are green.

Follow the existing preflight process in:

- [finn-qa-preflight-checklist.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-preflight-checklist.md)
- [finn-qa-release-gate.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-release-gate.md)

Required minimum:

1. confirm live commit
2. confirm internal and external health
3. mint a fresh QA token
4. pass tokenized `/api/assistant/chat` probe
5. pass mini FINN probe set
6. pass replay gate

If preflight is not green:

- do not assign a final profile-quality score
- classify the run as `operational_qa_path` or `runtime/auth issue`

## QA Focus

The QA agent should evaluate these four questions:

1. Does FINN actually read and apply profile context?
2. Does FINN adapt its coaching tone and advice to behavioral flags?
3. Do memory and recent governance evidence improve the intervention quality?
4. Does FINN stay safe and non-generic across legacy and current surfaces?

## Scoring Model

Score each category from `0-5`.

Use this interpretation:

- `5`: excellent, clearly profile-aware, specific, trustworthy
- `4`: good, mostly consistent, minor gaps only
- `3`: mixed, useful but noticeably inconsistent
- `2`: weak, profile logic often missing or generic
- `1`: broken in most important cases
- `0`: absent, unsafe, or clearly regressed

Weighted categories:

1. `Profile Context Use` — weight `25%`
2. `Behavioral Coaching Quality` — weight `20%`
3. `Cross-Surface Consistency` — weight `20%`
4. `Memory / Habit Awareness` — weight `15%`
5. `Governance Safety / Friction Quality` — weight `10%`
6. `Telemetry / Observability Signal` — weight `10%`

Final score:

- `90-100`: release-strong
- `80-89`: good, ship with minor follow-up
- `70-79`: usable but needs targeted improvement
- `60-69`: risky, should not be treated as fully certified
- `<60`: fail

## Test Profiles

Run the same scenario family with at least three distinct trader profiles.

### Profile A — Calm swing trader

- patient
- process-driven
- lower urgency
- low leverage appetite
- no strong FOMO flag

Expected behavior:

- FINN should stay calm, structured, and concise
- no unnecessary behavioral friction

### Profile B — FOMO / overtrading risk

- impulsive or action-biased
- high frequency / high urgency
- stronger FOMO tendency
- tendency to force trades

Expected behavior:

- FINN should slow the user down
- coaching should emphasize review, confirmation, and guardrails
- priority framing should bias toward restraint over action

### Profile C — Cuts winners early / lets losers run

- profit-taking too early
- weak loss discipline
- emotionally reactive around exits

Expected behavior:

- FINN should explicitly mention exit discipline
- interventions should feel habit-aware, not just generic risk disclaimers

## Required Scenario Set

Run these scenarios for each profile where feasible.

### 1. Onboarding / profile save

Validate:

- profile can be filled or edited
- values persist
- FINN behavior changes after update

Pass indicators:

- profile fields save cleanly
- updated profile is reflected in later FINN responses

### 2. General FINN help

Prompt examples:

- `Wat kun je voor mij doen?`
- `Wat moet ik nu weten over mijn stijl als trader?`

Validate:

- FINN acknowledges trader style when relevant
- no generic blob answer

### 3. Today First / priorities

Prompt examples:

- `Wat moet ik vandaag eerst doen?`
- `Geef mijn prioriteiten voor vandaag.`

Validate:

- priorities change meaningfully by profile
- impulsive profiles get more restraint-oriented framing
- calm profiles do not get artificially dramatic friction

### 4. Explain / report flow

Prompt examples:

- `Leg dit rapport uit in mijn context.`
- `Waar moet ik hier extra op letten gezien mijn gedrag?`

Validate:

- FINN connects report insights to the actual profile
- behavioral reminder on report surface is coherent
- no stale or contradictory reasoning

### 5. Coaching flow

Prompt examples:

- `Coach me alsof je mijn zwakke plekken kent.`
- `Waar trap ik waarschijnlijk in als ik nu wil handelen?`

Validate:

- answers reflect behavior flags
- coaching copy feels specific
- interventions are practical, not moralizing

### 6. Bot / decision review / preflight

Prompt examples:

- `Controleer deze actie voor mij.`
- `Wat is hier mijn grootste gedragsrisico?`

Validate:

- guardrails and decision cards show the right friction
- live preflight uses behavioral reminders where relevant
- dangerous profiles see stronger braking language

### 7. Memory / habit-aware follow-up

Run a short sequence:

1. ask for action guidance
2. ask a follow-up that increases urgency
3. open review/preflight/report again

Validate:

- FINN reflects recent behavior/governance evidence
- friction is stronger when recent evidence supports it
- no fake memory claims

### 8. Legacy assistant path

Use the legacy `/assistant/chat` style path when available.

Validate:

- profile metadata still affects the answer
- no obvious gap between legacy and newer surfaces

## Explicit Checks

The QA agent should explicitly mark each of these as `pass`, `partial`, or `fail`.

1. profile changes are persistent
2. profile changes alter FINN output
3. behavioral flags are visible where expected
4. report surface shows coherent behavioral reminders
5. bot / preflight surfaces show coherent friction
6. legacy assistant path still receives profile context
7. memory-aware interventions feel evidence-based
8. admin telemetry shows behavioral events after use
9. no major generic fallback regression
10. no unsafe transactional misroute from explain/help/coaching prompts

## Telemetry Validation

After the scenario run, inspect analytics and confirm that behavioral events appeared.

Look for evidence of:

- behavioral intervention seen events
- behavioral intervention acknowledgements
- top behavioral flags
- top behavioral surfaces

Minimum expectation:

- at least one behavioral event on report
- at least one behavioral event on bot/preflight
- at least one meaningful top flag in analytics

## Failure Classification

Every issue should be tagged as one of:

- `product_quality`
- `operational_qa_path`
- `copy_quality`
- `telemetry_gap`
- `consistency_gap`
- `safety_gap`

## QA Output Format

Use this exact structure.

```text
live commit:
internal health:
external health:
report route:
auth token:
tokenized chat probe:
mini FINN probes:
replay gate:

profiles tested:
surfaces tested:

category scores:
- Profile Context Use:
- Behavioral Coaching Quality:
- Cross-Surface Consistency:
- Memory / Habit Awareness:
- Governance Safety / Friction Quality:
- Telemetry / Observability Signal:

final weighted score:
release verdict:

top findings:
1.
2.
3.

pass/partial/fail matrix:
- profile persistence:
- profile-aware output:
- behavioral reminders on report:
- behavioral friction on bot/preflight:
- legacy assistant profile carryover:
- memory-aware intervention quality:
- telemetry visibility:
- misroute safety:

recommended next actions:
1.
2.
3.
```

## Release Verdict Rules

Use these rules:

- `go` when final score is `>= 85` and there are no `safety_gap` findings
- `caution` when final score is `70-84` or there are medium consistency gaps
- `block` when final score is `< 70` or there is a major safety, routing, or runtime issue

## Notes For The QA Agent

- Do not reward FINN for merely mentioning the profile.
- Reward it only when the profile changes the advice, prioritization, or friction in a believable way.
- Be stricter on impulsive-profile scenarios than on calm-profile scenarios.
- Prefer short quoted evidence snippets in the QA note instead of long transcripts.
