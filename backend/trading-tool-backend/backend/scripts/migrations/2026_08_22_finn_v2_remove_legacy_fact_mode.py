"""Backfill legacy FACT artifacts and restrict FINN V2 persistence to canonical modes."""

SQL = """
UPDATE finn_v2_runs
SET interaction_mode = 'READ',
    response_json = CASE WHEN response_json->>'mode' = 'FACT'
        THEN jsonb_set(response_json, '{mode}', '"READ"'::jsonb, true) ELSE response_json END
WHERE interaction_mode = 'FACT' OR response_json->>'mode' = 'FACT';

UPDATE finn_v2_orchestrator_results SET interaction_mode = 'READ' WHERE interaction_mode = 'FACT';

UPDATE finn_v2_reasoning_results
SET mode = 'READ',
    result_json = CASE WHEN result_json->>'mode' = 'FACT'
        THEN jsonb_set(result_json, '{mode}', '"READ"'::jsonb, true) ELSE result_json END
WHERE mode = 'FACT' OR result_json->>'mode' = 'FACT';

UPDATE finn_v2_verified_responses
SET mode = 'READ',
    response_json = CASE WHEN response_json->>'mode' = 'FACT'
        THEN jsonb_set(response_json, '{mode}', '"READ"'::jsonb, true) ELSE response_json END
WHERE mode = 'FACT' OR response_json->>'mode' = 'FACT';

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
