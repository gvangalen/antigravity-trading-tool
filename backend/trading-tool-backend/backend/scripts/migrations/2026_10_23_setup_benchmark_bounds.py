"""Move setup eligibility to the owner's combined benchmark score.

Legacy category filters have different meaning. Clear them so an old setup
cannot silently authorize a buy under the new combined-score rule. Pause bots
attached to those setups before clearing: calendar DCA may otherwise treat a
missing filter as an intentional unfiltered schedule.
"""

SQL = """
ALTER TABLE setups
  ADD COLUMN IF NOT EXISTS min_benchmark_score NUMERIC,
  ADD COLUMN IF NOT EXISTS max_benchmark_score NUMERIC;

UPDATE bot_configs AS bot SET is_active = FALSE
FROM strategies AS strategy, setups AS setup
WHERE bot.strategy_id = strategy.id
  AND strategy.setup_id = setup.id
  AND bot.user_id = setup.user_id
  AND (setup.min_market_score IS NOT NULL OR setup.max_market_score IS NOT NULL
    OR setup.min_macro_score IS NOT NULL OR setup.max_macro_score IS NOT NULL
    OR setup.min_technical_score IS NOT NULL OR setup.max_technical_score IS NOT NULL);

UPDATE setups SET
  min_market_score = NULL, max_market_score = NULL,
  min_macro_score = NULL, max_macro_score = NULL,
  min_technical_score = NULL, max_technical_score = NULL
WHERE min_market_score IS NOT NULL OR max_market_score IS NOT NULL
   OR min_macro_score IS NOT NULL OR max_macro_score IS NOT NULL
   OR min_technical_score IS NOT NULL OR max_technical_score IS NOT NULL;
"""
