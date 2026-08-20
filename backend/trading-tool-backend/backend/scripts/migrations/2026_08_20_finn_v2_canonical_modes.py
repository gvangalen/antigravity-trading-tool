"""Expand FINN Core V2 mode constraints to the canonical Blocks 1-8 runtime modes."""

SQL = """
ALTER TABLE finn_v2_runs
    DROP CONSTRAINT IF EXISTS finn_v2_runs_interaction_mode_check,
    DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_interaction_mode,
    ADD CONSTRAINT ck_finn_v2_runs_interaction_mode
    CHECK (
        interaction_mode IS NULL
        OR interaction_mode IN (
            'READ',
            'EVALUATE',
            'CREATE_PROPOSAL',
            'ACTION_PROPOSAL',
            'CLARIFICATION',
            'CONFIRMATION',
            'EXECUTION',
            'UNAVAILABLE',
            'CAPABILITY',
            'FACT',
            'EVALUATION',
            'PROPOSAL',
            'ACTION'
        )
    );

ALTER TABLE finn_v2_orchestrator_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode,
    ADD CONSTRAINT ck_finn_v2_orchestrator_mode
    CHECK (
        interaction_mode IN (
            'READ',
            'EVALUATE',
            'CREATE_PROPOSAL',
            'ACTION_PROPOSAL',
            'CLARIFICATION',
            'CONFIRMATION',
            'EXECUTION',
            'UNAVAILABLE',
            'CAPABILITY',
            'FACT',
            'EVALUATION',
            'PROPOSAL',
            'ACTION'
        )
    );

ALTER TABLE finn_v2_reasoning_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode,
    ADD CONSTRAINT ck_finn_v2_reasoning_mode
    CHECK (
        mode IN (
            'READ',
            'EVALUATE',
            'CREATE_PROPOSAL',
            'ACTION_PROPOSAL',
            'CLARIFICATION',
            'CONFIRMATION',
            'EXECUTION',
            'UNAVAILABLE',
            'CAPABILITY',
            'FACT',
            'EVALUATION',
            'PROPOSAL',
            'ACTION'
        )
    );

ALTER TABLE finn_v2_verified_responses
    DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode,
    ADD CONSTRAINT ck_finn_v2_verified_mode
    CHECK (
        mode IN (
            'READ',
            'EVALUATE',
            'CREATE_PROPOSAL',
            'ACTION_PROPOSAL',
            'CLARIFICATION',
            'CONFIRMATION',
            'EXECUTION',
            'UNAVAILABLE',
            'CAPABILITY',
            'FACT',
            'EVALUATION',
            'PROPOSAL',
            'ACTION'
        )
    );
"""


ROLLBACK_SQL = """
ALTER TABLE finn_v2_verified_responses
    DROP CONSTRAINT IF EXISTS ck_finn_v2_verified_mode,
    ADD CONSTRAINT ck_finn_v2_verified_mode
    CHECK (mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));

ALTER TABLE finn_v2_reasoning_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_reasoning_mode,
    ADD CONSTRAINT ck_finn_v2_reasoning_mode
    CHECK (mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));

ALTER TABLE finn_v2_orchestrator_results
    DROP CONSTRAINT IF EXISTS ck_finn_v2_orchestrator_mode,
    ADD CONSTRAINT ck_finn_v2_orchestrator_mode
    CHECK (interaction_mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'UNAVAILABLE'));

ALTER TABLE finn_v2_runs
    DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_interaction_mode,
    ADD CONSTRAINT ck_finn_v2_runs_interaction_mode
    CHECK (interaction_mode IS NULL OR interaction_mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE'));
"""
