"""Allow FINN V2 capability mode across persisted run, orchestrator, reasoning, and delivery records."""

SQL = """
ALTER TABLE IF EXISTS finn_v2_runs
    DROP CONSTRAINT IF EXISTS finn_v2_runs_interaction_mode_check,
    DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_interaction_mode;

ALTER TABLE IF EXISTS finn_v2_runs
    ADD CONSTRAINT ck_finn_v2_runs_interaction_mode
    CHECK (
        interaction_mode IS NULL
        OR interaction_mode IN ('FACT', 'CAPABILITY', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE')
    );

ALTER TABLE IF EXISTS finn_v2_orchestrator_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode;

ALTER TABLE IF EXISTS finn_v2_orchestrator_results
    ADD CONSTRAINT ck_finn_v2_orchestrator_mode
    CHECK (interaction_mode IN ('FACT', 'CAPABILITY', 'EVALUATION', 'PROPOSAL', 'ACTION', 'UNAVAILABLE'));

ALTER TABLE IF EXISTS finn_v2_reasoning_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode;

ALTER TABLE IF EXISTS finn_v2_reasoning_results
    ADD CONSTRAINT ck_finn_v2_reasoning_mode
    CHECK (mode IN ('FACT', 'CAPABILITY', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));

ALTER TABLE IF EXISTS finn_v2_verified_responses
    DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode;

ALTER TABLE IF EXISTS finn_v2_verified_responses
    ADD CONSTRAINT ck_finn_v2_verified_mode
    CHECK (mode IN ('FACT', 'CAPABILITY', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));
"""


ROLLBACK_SQL = """
ALTER TABLE IF EXISTS finn_v2_runs
    DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_interaction_mode;

ALTER TABLE IF EXISTS finn_v2_runs
    ADD CONSTRAINT ck_finn_v2_runs_interaction_mode
    CHECK (
        interaction_mode IS NULL
        OR interaction_mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE')
    );

ALTER TABLE IF EXISTS finn_v2_orchestrator_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode;

ALTER TABLE IF EXISTS finn_v2_orchestrator_results
    ADD CONSTRAINT ck_finn_v2_orchestrator_mode
    CHECK (interaction_mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'UNAVAILABLE'));

ALTER TABLE IF EXISTS finn_v2_reasoning_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode;

ALTER TABLE IF EXISTS finn_v2_reasoning_results
    ADD CONSTRAINT ck_finn_v2_reasoning_mode
    CHECK (mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));

ALTER TABLE IF EXISTS finn_v2_verified_responses
    DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode;

ALTER TABLE IF EXISTS finn_v2_verified_responses
    ADD CONSTRAINT ck_finn_v2_verified_mode
    CHECK (mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));
"""
