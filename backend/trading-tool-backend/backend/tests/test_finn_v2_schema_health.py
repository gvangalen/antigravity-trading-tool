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
            return self.metadata
        return None


class _Connection:
    def __init__(self, metadata):
        self.cursor_instance = _Cursor(metadata)

    def cursor(self):
        return self.cursor_instance


def test_schema_health_accepts_the_conversation_context_contract():
    connection = _Connection(("jsonb", "jsonb", "NO", "'{}'::jsonb"))

    assert_finn_v2_schema(connection)

    assert any("SELECT context_json FROM finn_v2_conversations" in statement for statement, _ in connection.cursor_instance.executed)


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
    connection = _Connection(metadata)

    with pytest.raises(FinnV2SchemaHealthError, match=error_code):
        assert_finn_v2_schema(connection)
