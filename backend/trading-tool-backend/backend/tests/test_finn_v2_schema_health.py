import pytest

from backend.scripts.check_finn_v2_schema import FinnV2SchemaHealthError, assert_finn_v2_schema


class _Cursor:
    def __init__(self, metadata):
        self.metadata = metadata
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=None):
        self.executed.append((statement, parameters))

    def fetchone(self):
        if self.executed[-1][1]:
            parameters = self.executed[-1][1]
            if isinstance(self.metadata, dict) and len(parameters) == 2:
                return self.metadata.get((parameters[0], parameters[1]))
            if isinstance(self.metadata, dict):
                return None
            return self.metadata
        return None


class _Connection:
    def __init__(self, metadata):
        self.cursor_instance = _Cursor(metadata)

    def cursor(self):
        return self.cursor_instance


def test_schema_health_accepts_the_conversation_context_contract():
    connection = _Connection({
        ("finn_v2_evidence_artifacts", "information_scope"): ("text", "text", "YES", None),
        ("finn_v2_tool_calls", "operation_id"): ("text", "text", "YES", None),
        ("finn_v2_tool_calls", "operation_contract_version"): ("text", "text", "YES", None),
        ("finn_v2_evidence_artifacts", "operation_id"): ("text", "text", "YES", None),
        ("finn_v2_evidence_artifacts", "operation_contract_version"): ("text", "text", "YES", None),
        ("finn_v2_conversations", "context_json"): ("jsonb", "jsonb", "NO", "'{}'::jsonb"),
        ("user_indicator_configs", "config_json"): ("jsonb", "jsonb", "NO", "'{}'::jsonb"),
        ("user_indicator_configs", "provenance"): ("text", "text", "NO", "'product_api'::text"),
        ("user_indicator_configs", "source_record_id"): ("bigint", "int8", "YES", None),
        ("user_indicator_configs", "updated_at"): ("timestamp without time zone", "timestamp", "NO", "CURRENT_TIMESTAMP"),
        ("finn_v2_indicator_config_reconciliations", "source_record_ids"): ("jsonb", "jsonb", "NO", None),
        ("finn_v2_indicator_config_reconciliations", "legacy_config_json"): ("jsonb", "jsonb", "NO", "'{}'::jsonb"),
        ("finn_v2_indicator_config_reconciliations", "status"): ("text", "text", "NO", "'asset_scope_required'::text"),
    })

    assert_finn_v2_schema(connection)

    assert any("SELECT context_json FROM finn_v2_conversations" in statement for statement, _ in connection.cursor_instance.executed)
    assert any("SELECT operation_id, operation_contract_version FROM finn_v2_tool_calls" in statement for statement, _ in connection.cursor_instance.executed)


@pytest.mark.parametrize(
    ("metadata", "error_code"),
    [
        (None, "finn_v2_schema_missing_column"),
        (("json", "json", "NO", "'{}'::jsonb"), "finn_v2_schema_invalid_type"),
        (("jsonb", "jsonb", "YES", "'{}'::jsonb"), "finn_v2_schema_invalid_nullability"),
        (("jsonb", "jsonb", "NO", None), "finn_v2_schema_invalid_default"),
    ],
)
def test_schema_health_rejects_incompatible_context_contract(metadata, error_code):
    connection = _Connection({
        ("finn_v2_evidence_artifacts", "information_scope"): ("text", "text", "YES", None),
        ("finn_v2_tool_calls", "operation_id"): ("text", "text", "YES", None),
        ("finn_v2_tool_calls", "operation_contract_version"): ("text", "text", "YES", None),
        ("finn_v2_evidence_artifacts", "operation_id"): ("text", "text", "YES", None),
        ("finn_v2_evidence_artifacts", "operation_contract_version"): ("text", "text", "YES", None),
        ("finn_v2_conversations", "context_json"): metadata,
        ("user_indicator_configs", "config_json"): ("jsonb", "jsonb", "NO", "'{}'::jsonb"),
        ("user_indicator_configs", "provenance"): ("text", "text", "NO", "'product_api'::text"),
        ("user_indicator_configs", "source_record_id"): ("bigint", "int8", "YES", None),
        ("user_indicator_configs", "updated_at"): ("timestamp without time zone", "timestamp", "NO", "CURRENT_TIMESTAMP"),
        ("finn_v2_indicator_config_reconciliations", "source_record_ids"): ("jsonb", "jsonb", "NO", None),
        ("finn_v2_indicator_config_reconciliations", "legacy_config_json"): ("jsonb", "jsonb", "NO", "'{}'::jsonb"),
        ("finn_v2_indicator_config_reconciliations", "status"): ("text", "text", "NO", "'asset_scope_required'::text"),
    })

    with pytest.raises(FinnV2SchemaHealthError, match=error_code):
        assert_finn_v2_schema(connection)
