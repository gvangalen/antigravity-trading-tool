"""Capture the linked plan when a manual order opens, without inferring adherence.

Older orders remain unchanged: their opening plan cannot be reconstructed from
the current strategy or setup without rewriting history.
"""

SQL = """
CREATE OR REPLACE FUNCTION finn_capture_order_plan() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO finn_trade_order_context (user_id, order_id, decision_id, plan_snapshot)
  SELECT NEW.user_id, NEW.id, NEW.decision_id,
    CASE
      WHEN p.decision_id IS NOT NULL THEN jsonb_build_object(
        'entry_plan', p.entry_plan, 'stop_loss', p.stop_loss,
        'targets', p.targets, 'risk', p.risk_json
      )
      WHEN NEW.decision_id IS NULL AND NEW.side = 'buy'
           AND s.id IS NOT NULL AND st.id IS NOT NULL THEN jsonb_build_object(
        'linked_setup', jsonb_build_object(
          'id', st.id, 'name', st.name, 'symbol', st.symbol,
          'market_id', st.market_id, 'timeframe', st.timeframe,
          'min_benchmark_score', st.min_benchmark_score,
          'max_benchmark_score', st.max_benchmark_score,
          'min_market_score', st.min_market_score,
          'max_market_score', st.max_market_score,
          'min_macro_score', st.min_macro_score,
          'max_macro_score', st.max_macro_score,
          'min_technical_score', st.min_technical_score,
          'max_technical_score', st.max_technical_score
        ),
        'linked_strategy', jsonb_build_object(
          'id', s.id, 'name', s.name, 'execution_mode', s.execution_mode,
          'base_amount', s.base_amount, 'entry', s.entry,
          'stop_loss', s.stop_loss, 'targets', s.targets,
          'price_currency', s.data->>'price_currency'
        ),
        'order_context', 'manual_order_from_linked_bot',
        'plan_adherence', 'not_assessed'
      )
      ELSE NULL
    END
  FROM (SELECT 1) seed
  LEFT JOIN bot_trade_plans p ON p.decision_id = NEW.decision_id
    AND p.user_id = NEW.user_id
  LEFT JOIN bot_configs b ON b.id = NEW.bot_id AND b.user_id = NEW.user_id
  LEFT JOIN strategies s ON s.id = b.strategy_id AND s.user_id = NEW.user_id
  LEFT JOIN setups st ON st.id = s.setup_id AND st.user_id = NEW.user_id;
  RETURN NEW;
END $$;
"""
