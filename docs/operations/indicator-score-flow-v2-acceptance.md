# Indicator score flow 2.0: acceptance

The canonical path is: owner and asset indicator configuration → dated raw reading → normalized indicator score using that configuration → weighted category score → dated daily evidence → current benchmark → setup match. FINN, Analyse, Mijn Plan, reports, mobile, and paper bot decisions must read that path. The paper bot continues to run when the match is unavailable; it must not invent a score.

## Build checks

- Apply `2026_10_06_indicator_score_flow_v2.py` before starting API or workers. The new daily score evidence fields and indexes are required.
- Run root `pytest -q`, frontend `npm run build`, mobile `npm run typecheck`, and the migration plan validator.
- Verify the configured snapshot worker refreshes market, macro, and technical measurements for owner and asset. Macro refresh must retain the selection and preserve different dated observations; an unchanged provider observation must not create a new reading.
- Verify a new Price, Volume, DXY, S&P 500, Gold, or Oil configuration queues a bounded historical-source bootstrap after the configuration is committed. The hourly recovery sweep must cover existing deficient configurations. Only original dated, completed observations may enter history; retries must not duplicate source days or manufacture a score.
- For derived DXY, verify a historical day is admitted only if all six currency components are measured. When no Twelve Data key exists, the Yahoo index fallback must use its own dated history. A failed provider leaves the category unavailable and is retried without changing the user's indicator selection.

## Independent QA on a test account

1. Configure different market, macro, and technical indicators for two assets. Give one indicator a custom five-band curve and a non-default weight. Verify the indicator score, weighted category, benchmark, FINN readback, and mobile values agree with the saved configuration.
2. Check one asset with at least five dated price/volume observations and one with too little history. Absolute levels must use the asset's history; insufficient history must show no current score rather than a high bucket from the raw price or volume.
3. Repeat with an absolute macro level such as S&P 500 or gold. Fewer than five distinct dated readings must remain unscored; after sufficient observations the selected bucket must be reproducible from the recorded normal value.
   Confirm DXY separately: the same chosen source supplies the current reading and its dated history, and Analyse explains the exact observed-day count while history is incomplete. After backfill, the latest indicator row, macro group score, FINN readback and dated benchmark must agree without re-adding the indicator.
4. Edit a selected indicator's rule or weight. Before the next daily rebuild, the old category, benchmark, and setup match must become unavailable. After rebuild they must reflect the new configuration. Repeat after a new provider observation and after one source passes its age limit.
5. Verify Analyse shows no numeric current score or contributor explanation for a stale component. The setup gauge has no benchmark weight; market, macro, and technical weights sum to 100%. FINN, reports, web and mobile must not substitute an old AI master score or turn missing data into zero.
6. Check a Smart DCA at an exact curve boundary and with a missing component. The calculated paper amount must use the current benchmark only; missing evidence must produce no amount. Verify fixed DCA remains independent of score and that an existing paper bot is not stopped merely because a setup match is absent.
7. Compare at least 20 configured assets across users. Ensure each owner sees only their own selections and matches. Inspect worker duration, provider rate limits, and the bounded refresh window; a deferred scope should refresh on later rounds.

Record backend and frontend SHA, source observation times, config revision times, score evidence, daily calculation time, and bot decision IDs for each decisive check. Do not mark actual score-driven execution accepted from a hypothetical FINN calculation alone.
