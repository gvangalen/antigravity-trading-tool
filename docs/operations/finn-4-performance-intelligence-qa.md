# FINN 4.0 QA Suite — Performance Intelligence

Last updated: 2026-06-03

## Purpose

This suite adds a third measurable QA layer on top of the existing FINN evaluation stack:

1. FINN Core QA
2. FINN Operator QA
3. FINN Performance Intelligence QA

The goal is to measure whether FINN helps the trader understand:

- what patterns keep repeating
- what those patterns cost
- what their strongest and weakest habits are
- what lessons can be extracted from historical trades
- whether coaching is actually helping over time

This suite should stay read-only and evidence-first.
It is not intended to test execution authority.

See also:

- [FINN 4.0 Latency-Green Checklist](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-4-latency-green-checklist.md)

## Principle

The question is not:

> Does FINN sound insightful?

The question is:

> Does FINN produce grounded performance intelligence that helps the user improve?

## Relationship To Existing QA

This suite does not replace the existing QA layers.

- FINN Core QA still protects:
  - conversation
  - education
  - product explain
  - context
  - coaching
  - tool usage
  - reliability

- FINN Operator QA still protects:
  - decision review
  - plan adherence
  - outcome tracking
  - portfolio intelligence
  - priority engine

- FINN Performance Intelligence QA adds:
  - outcome memory
  - personal performance intelligence
  - behavioral intelligence
  - learning engine
  - coaching evolution

## Categories

### 1. Outcome Memory

#### Goal

Measure whether FINN remembers repeated outcome patterns and links behavior to downstream results.

#### What good looks like

- identifies repeated historical patterns
- uses explicit prior results
- connects behavior to outcomes
- distinguishes weak evidence from strong evidence

#### What to check

- sample size awareness
- explicit mention of repeated pattern
- net effect or cost
- grounded confidence language

### 2. Personal Performance Intelligence

#### Goal

Measure whether FINN can describe how well the user is trading, not only whether they made or lost money.

#### What good looks like

- names strengths
- names weaknesses
- compares periods
- identifies biggest performance leaks
- stays grounded in observed evidence

#### What to check

- strength / weakness specificity
- period comparison
- performance framing beyond raw PnL
- concrete explanation of where quality is leaking

### 3. Behavioral Intelligence

#### Goal

Measure whether FINN can recognize recurring behavior mistakes and explain what they cost.

#### Required patterns

- FOMO
- overtrading
- impulsive trading
- taking profit too early
- exiting too late

#### What good looks like

- identifies the behavior pattern
- explains why it is risky
- explains what it costs
- gives a useful interruption step

### 4. Learning Engine

#### Goal

Measure whether FINN can extract practical lessons from historical trades and journal signals.

#### What good looks like

- identifies repeated mistakes
- extracts lessons from prior trades
- turns patterns into rules
- proposes concrete improvement actions

#### What to check

- lesson quality
- pattern-to-rule translation
- specificity of improvement advice
- evidence grounding

### 5. Coaching Evolution

#### Goal

Measure whether FINN can explain whether the user is improving or regressing over time.

#### What good looks like

- compares prior and current behavior
- says whether the user is improving or slipping
- names what changed
- suggests the next best rule or intervention

#### What to check

- time-based comparison
- evidence of growth or decline
- coaching specificity
- practical next step

## Scoring Model

Each category is scored from `0-100`.

Use five subcriteria per category, each scored `0-20`:

1. Pattern Recognition
2. Evidence Grounding
3. Outcome Linking
4. Actionability
5. Consistency

### Interpretation

- `90-100` = strong and trustworthy
- `80-89` = good and usable
- `70-79` = useful but still leaky
- `60-69` = mixed
- `<60` = not reliable enough yet

## Prompt Design

Use compact, repeatable prompts with explicit scenario wording.

### Outcome Memory

- `Wat onthoudt Finn van mijn uitkomsten?`
- `Welk gedrag kost me de laatste maand het meeste?`
- `Welke fouten blijven terugkomen in mijn resultaten?`
- `Wat zie je terugkeren in mijn verliestrades?`

### Personal Performance Intelligence

- `Geef mijn performance score`
- `Hoe goed trade ik de laatste 30 dagen?`
- `Wat zegt Finn over mijn trading kwaliteit?`
- `Waar verlies ik het meeste discipline?`

### Behavioral Intelligence

- `Zie je FOMO-patronen in mijn gedrag?`
- `Overtrade ik?`
- `Handel ik te impulsief?`
- `Neem ik te vroeg winst of stap ik te laat uit?`

### Learning Engine

- `Wat leert mijn trade journal?`
- `Welke patronen zitten in mijn notities?`
- `Wat leren mijn post trade notities?`
- `Welke les moet ik uit mijn laatste trades trekken?`

### Coaching Evolution

- `Coach me op basis van mijn laatste fouten`
- `Wat is mijn grootste persoonlijke performance lek?`
- `Word ik beter of slechter als trader?`
- `Wat is mijn volgende beste coachregel?`

## Example Test Scenarios

### Outcome Memory

- repeated FOMO trades with loss-heavy outcomes
- same rule break across multiple reviews
- weak sample versus strong sample
- behavior pattern with measurable cost

### Personal Performance Intelligence

- strong waiting discipline but weak exits
- better week than month
- fewer overrides but still oversized positions
- good plan adherence with weak portfolio discipline

### Behavioral Intelligence

- FOMO after a missed move
- overtrading after multiple failed attempts
- taking profit too early
- refusing to exit after invalidation

### Learning Engine

- repeated poor entries
- repeated outside-plan trades
- journal notes show recurring impatience
- journal notes show better trades after confirmation

### Coaching Evolution

- discipline improving while returns are mixed
- returns improving while risk discipline worsens
- coaching helped entries but not exits
- user is better at waiting, still weak at sizing

## Output Format

Every FINN 4.0 QA report should return:

## FINN Core

- Conversatie: X
- Trading Kennis: X
- Productkennis: X
- Context Awareness: X
- Coaching: X
- Tool Usage: X
- Reliability: X

### Overall Core Score: X

## FINN Operator

- Decision Review: X
- Plan Adherence: X
- Outcome Tracking: X
- Portfolio Intelligence: X
- Priority Engine: X

### Overall Operator Score: X

## FINN Performance Intelligence

- Outcome Memory: X
- Personal Performance Intelligence: X
- Behavioral Intelligence: X
- Learning Engine: X
- Coaching Evolution: X

### Overall Performance Intelligence Score: X

## Per Category

- score
- strong points
- weak points
- biggest opportunities
- priorities for the next tranche

## Certification

### FINN 4.0 Performance Certified

Conditions:

- Performance Intelligence Score >= 90
- no category below 80

## Suggested Execution Order

1. run FINN Core QA
2. run FINN Operator QA
3. run FINN Performance Intelligence QA
4. compare against the latest valid baseline
5. publish one combined report

## Assets

- Full promptset: [finn-qa-promptset-full.json](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-full.json)
- Performance promptset: [finn-qa-promptset-performance-intelligence.json](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-qa-promptset-performance-intelligence.json)
- Replay script: [run_finn_qa_replay.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_finn_qa_replay.py)
