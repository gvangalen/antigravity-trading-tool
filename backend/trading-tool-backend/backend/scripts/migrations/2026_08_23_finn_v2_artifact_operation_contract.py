"""Persist the resolved FINN V2 operation identity on the evidence ledger."""

SQL = """
ALTER TABLE finn_v2_tool_calls
    ADD COLUMN IF NOT EXISTS operation_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS operation_contract_version TEXT NULL;

ALTER TABLE finn_v2_evidence_artifacts
    ADD COLUMN IF NOT EXISTS operation_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS operation_contract_version TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_operation_contract
    ON finn_v2_tool_calls (operation_id, operation_contract_version);
CREATE INDEX IF NOT EXISTS idx_finn_v2_evidence_operation_contract
    ON finn_v2_evidence_artifacts (operation_id, operation_contract_version);
"""


ROLLBACK_SQL = """
DROP INDEX IF EXISTS idx_finn_v2_evidence_operation_contract;
DROP INDEX IF EXISTS idx_finn_v2_tool_calls_operation_contract;
ALTER TABLE finn_v2_evidence_artifacts
    DROP COLUMN IF EXISTS operation_contract_version,
    DROP COLUMN IF EXISTS operation_id;
ALTER TABLE finn_v2_tool_calls
    DROP COLUMN IF EXISTS operation_contract_version,
    DROP COLUMN IF EXISTS operation_id;
"""
