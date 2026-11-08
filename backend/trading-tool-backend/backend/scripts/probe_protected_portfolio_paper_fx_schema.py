"""Read only the two Paper/FX price-column types through protected QA."""

from __future__ import annotations


EXPECTED_COLUMNS = (
    ("bot_orders", "executed_price_eur"),
    ("bot_ledger", "price_eur"),
)
SAFE_DATA_TYPES = frozenset({
    "numeric", "decimal", "double precision", "real",
    "integer", "bigint", "smallint",
})


def _bounded_dimension(value):
    if value is None:
        return None
    if type(value) is int and 0 <= value <= 1000:
        return value
    raise RuntimeError("portfolio_paper_fx_schema_unexpected_dimension")


def run() -> dict:
    from backend.utils.db import get_db_connection

    connection = get_db_connection()
    if connection is None:
        raise RuntimeError("portfolio_paper_fx_schema_database_unavailable")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT table_name,column_name,data_type,numeric_precision,numeric_scale
                   FROM information_schema.columns
                   WHERE table_schema='public'
                     AND ((table_name='bot_orders' AND column_name='executed_price_eur')
                       OR (table_name='bot_ledger' AND column_name='price_eur'))"""
            )
            rows = cursor.fetchall()
        columns = {}
        for table, column, data_type, precision, scale in rows:
            if (table, column) not in EXPECTED_COLUMNS or (table, column) in columns:
                raise RuntimeError("portfolio_paper_fx_schema_unexpected_column")
            if data_type not in SAFE_DATA_TYPES:
                raise RuntimeError("portfolio_paper_fx_schema_unexpected_type")
            columns[(table, column)] = {
                "data_type": data_type,
                "numeric_precision": _bounded_dimension(precision),
                "numeric_scale": _bounded_dimension(scale),
            }
        if set(columns) != set(EXPECTED_COLUMNS):
            raise RuntimeError("portfolio_paper_fx_schema_missing_column")
        return {
            "result": "PASS",
            "columns": {f"{table}.{column}": columns[(table, column)]
                        for table, column in EXPECTED_COLUMNS},
        }
    finally:
        connection.close()
