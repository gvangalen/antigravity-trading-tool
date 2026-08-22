"""Backfill legacy FACT artifacts and restrict FINN V2 persistence to canonical modes."""

SQL = """
UPDATE finn_v2_runs
SET interaction_mode = CASE interaction_mode
        WHEN 'FACT' THEN 'READ'
        WHEN 'EVALUATION' THEN 'EVALUATE'
        WHEN 'PROPOSAL' THEN 'CREATE_PROPOSAL'
        WHEN 'ACTION' THEN 'ACTION_PROPOSAL'
        ELSE interaction_mode END,
    response_json = CASE response_json->>'mode'
        WHEN 'FACT' THEN jsonb_set(response_json, '{mode}', '"READ"'::jsonb, true)
        WHEN 'EVALUATION' THEN jsonb_set(response_json, '{mode}', '"EVALUATE"'::jsonb, true)
        WHEN 'PROPOSAL' THEN jsonb_set(response_json, '{mode}', '"CREATE_PROPOSAL"'::jsonb, true)
        WHEN 'ACTION' THEN jsonb_set(response_json, '{mode}', '"ACTION_PROPOSAL"'::jsonb, true)
        ELSE response_json END
WHERE interaction_mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION')
   OR response_json->>'mode' IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION');

UPDATE finn_v2_orchestrator_results
SET interaction_mode = CASE interaction_mode
        WHEN 'FACT' THEN 'READ'
        WHEN 'EVALUATION' THEN 'EVALUATE'
        WHEN 'PROPOSAL' THEN 'CREATE_PROPOSAL'
        WHEN 'ACTION' THEN 'ACTION_PROPOSAL'
        ELSE interaction_mode END
WHERE interaction_mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION');

UPDATE finn_v2_reasoning_results
SET mode = CASE mode
        WHEN 'FACT' THEN 'READ'
        WHEN 'EVALUATION' THEN 'EVALUATE'
        WHEN 'PROPOSAL' THEN 'CREATE_PROPOSAL'
        WHEN 'ACTION' THEN 'ACTION_PROPOSAL'
        ELSE mode END,
    result_json = CASE result_json->>'mode'
        WHEN 'FACT' THEN jsonb_set(result_json, '{mode}', '"READ"'::jsonb, true)
        WHEN 'EVALUATION' THEN jsonb_set(result_json, '{mode}', '"EVALUATE"'::jsonb, true)
        WHEN 'PROPOSAL' THEN jsonb_set(result_json, '{mode}', '"CREATE_PROPOSAL"'::jsonb, true)
        WHEN 'ACTION' THEN jsonb_set(result_json, '{mode}', '"ACTION_PROPOSAL"'::jsonb, true)
        ELSE result_json END
WHERE mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION')
   OR result_json->>'mode' IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION');

UPDATE finn_v2_verified_responses
SET mode = CASE mode
        WHEN 'FACT' THEN 'READ'
        WHEN 'EVALUATION' THEN 'EVALUATE'
        WHEN 'PROPOSAL' THEN 'CREATE_PROPOSAL'
        WHEN 'ACTION' THEN 'ACTION_PROPOSAL'
        ELSE mode END,
    response_json = CASE response_json->>'mode'
        WHEN 'FACT' THEN jsonb_set(response_json, '{mode}', '"READ"'::jsonb, true)
        WHEN 'EVALUATION' THEN jsonb_set(response_json, '{mode}', '"EVALUATE"'::jsonb, true)
        WHEN 'PROPOSAL' THEN jsonb_set(response_json, '{mode}', '"CREATE_PROPOSAL"'::jsonb, true)
        WHEN 'ACTION' THEN jsonb_set(response_json, '{mode}', '"ACTION_PROPOSAL"'::jsonb, true)
        ELSE response_json END
WHERE mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION')
   OR response_json->>'mode' IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION');

ALTER TABLE finn_v2_runs DROP CONSTRAINT IF EXISTS finn_v2_runs_interaction_mode_check, DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_interaction_mode;
ALTER TABLE finn_v2_runs ADD CONSTRAINT ck_finn_v2_runs_interaction_mode CHECK (interaction_mode IS NULL OR interaction_mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE'));

ALTER TABLE finn_v2_orchestrator_results DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode;
ALTER TABLE finn_v2_orchestrator_results ADD CONSTRAINT ck_finn_v2_orchestrator_mode CHECK (interaction_mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE'));

ALTER TABLE finn_v2_reasoning_results DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode;
ALTER TABLE finn_v2_reasoning_results ADD CONSTRAINT ck_finn_v2_reasoning_mode CHECK (mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE'));

ALTER TABLE finn_v2_verified_responses DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode;
ALTER TABLE finn_v2_verified_responses ADD CONSTRAINT ck_finn_v2_verified_mode CHECK (mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE'));
"""


ROLLBACK_SQL = """
ALTER TABLE finn_v2_runs DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_interaction_mode;
ALTER TABLE finn_v2_runs ADD CONSTRAINT ck_finn_v2_runs_interaction_mode CHECK (interaction_mode IS NULL OR interaction_mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE', 'FACT', 'EVALUATION', 'PROPOSAL', 'ACTION'));
ALTER TABLE finn_v2_orchestrator_results DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode;
ALTER TABLE finn_v2_orchestrator_results ADD CONSTRAINT ck_finn_v2_orchestrator_mode CHECK (interaction_mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE', 'FACT', 'EVALUATION', 'PROPOSAL', 'ACTION'));
ALTER TABLE finn_v2_reasoning_results DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode;
ALTER TABLE finn_v2_reasoning_results ADD CONSTRAINT ck_finn_v2_reasoning_mode CHECK (mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE', 'FACT', 'EVALUATION', 'PROPOSAL', 'ACTION'));
ALTER TABLE finn_v2_verified_responses DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode;
ALTER TABLE finn_v2_verified_responses ADD CONSTRAINT ck_finn_v2_verified_mode CHECK (mode IN ('CAPABILITY', 'READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE', 'FACT', 'EVALUATION', 'PROPOSAL', 'ACTION'));
"""
