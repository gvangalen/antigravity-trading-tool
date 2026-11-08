"""Secret-free checks for the protected read-only strategy schema audit."""

from contextlib import contextmanager

from backend.scripts.probe_protected_trader_strategy_schema import run
from backend.scripts.run_finn_production_qa import profile_error_category


EXPECTED_ROWS = [
    ("targets", "ARRAY", "_text", "YES"),
    ("market_id", "bigint", "int8", "YES"),
    ("data", "jsonb", "jsonb", "NO"),
    ("setup_type", "character varying", "varchar", "YES"),
    ("entry", "numeric", "numeric", "YES"),
    ("stop_loss", "numeric", "numeric", "YES"),
]


class Cursor:
    def __init__(self, columns, constraints, triggers):
        self.responses = [None, columns, constraints, triggers]
        self.index = -1
        self.statements = []

    def execute(self, sql, *_args):
        self.index += 1
        self.statements.append(sql)

    def fetchall(self):
        return self.responses[self.index]


class Connection:
    def __init__(self, columns, constraints=(), triggers=()):
        self.cursor_value = Cursor(columns, constraints, triggers)
        self.closed = False

    @contextmanager
    def cursor(self):
        yield self.cursor_value

    def close(self):
        self.closed = True


def test_schema_audit_reads_only_metadata_and_allowlisted_names(monkeypatch):
    from backend.utils import db

    conn = Connection(EXPECTED_ROWS,
                      [("strategies_market_id_fkey", "f", "market_id"),
                       ("private_constraint_name", "c", "entry")],
                      [("O",)])
    monkeypatch.setattr(db, "get_db_connection", lambda: conn)
    result = run()
    assert result["result"] == "PASS"
    assert result["type_contract_matches"] is True
    assert result["columns"]["targets"]["udt_name"] == "_text"
    assert result["constraints"] == {
        "strategies_market_id_fkey": {"kind": "FOREIGN_KEY", "columns": ["market_id"]}
    }
    assert result["other_constraint_rows"] == 1
    assert result["user_trigger_count"] == 1
    assert result["enabled_user_trigger_count"] == 1
    assert "private_constraint_name" not in str(result)
    assert conn.cursor_value.statements[0] == "SET TRANSACTION READ ONLY"
    assert all("SELECT" in query for query in conn.cursor_value.statements[1:])
    assert conn.closed


def test_schema_audit_reports_type_drift_without_raw_udt(monkeypatch):
    from backend.utils import db

    columns = [(name, "text", "private_type", nullable) if name == "targets"
               else (name, data_type, udt, nullable)
               for name, data_type, udt, nullable in EXPECTED_ROWS]
    conn = Connection(columns)
    monkeypatch.setattr(db, "get_db_connection", lambda: conn)
    result = run()
    assert result["result"] == "FAIL"
    assert result["columns"]["targets"] == {
        "data_type": "OTHER", "udt_name": "OTHER", "nullable": True,
        "matches_expected": False,
    }
    assert "private_type" not in str(result)


def test_schema_audit_sanitizes_unexpected_errors():
    assert profile_error_category(
        "trader_strategy_schema_audit", RuntimeError("private SQL error text")
    ) == "trader_strategy_schema_runtime_error"
