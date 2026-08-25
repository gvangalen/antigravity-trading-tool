"""Fail deployment before FINN V2 starts against an incompatible database schema."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Optional

from backend.utils.db import get_db_connection


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequiredColumn:
    table_name: str
    column_name: str
    udt_name: str
    nullable: bool
    default_fragment: Optional[str] = None


REQUIRED_FINN_V2_COLUMNS = (
    RequiredColumn(
        table_name="finn_v2_evidence_artifacts",
        column_name="information_scope",
        udt_name="text",
        nullable=True,
    ),
    RequiredColumn(
        table_name="finn_v2_tool_calls",
        column_name="operation_id",
        udt_name="text",
        nullable=True,
    ),
    RequiredColumn(
        table_name="finn_v2_tool_calls",
        column_name="operation_contract_version",
        udt_name="text",
        nullable=True,
    ),
    RequiredColumn(
        table_name="finn_v2_evidence_artifacts",
        column_name="operation_id",
        udt_name="text",
        nullable=True,
    ),
    RequiredColumn(
        table_name="finn_v2_evidence_artifacts",
        column_name="operation_contract_version",
        udt_name="text",
        nullable=True,
    ),
    RequiredColumn(
        table_name="finn_v2_conversations",
        column_name="context_json",
        udt_name="jsonb",
        nullable=False,
        default_fragment="'{}'::jsonb",
    ),
    RequiredColumn(
        table_name="user_indicator_configs",
        column_name="config_json",
        udt_name="jsonb",
        nullable=False,
        default_fragment="'{}'::jsonb",
    ),
    RequiredColumn(
        table_name="user_indicator_configs",
        column_name="provenance",
        udt_name="text",
        nullable=False,
        default_fragment="'product_api'",
    ),
    RequiredColumn(
        table_name="user_indicator_configs",
        column_name="source_record_id",
        udt_name="int8",
        nullable=True,
    ),
    RequiredColumn(
        table_name="user_indicator_configs",
        column_name="updated_at",
        udt_name="timestamp",
        nullable=False,
    ),
    RequiredColumn(
        table_name="finn_v2_indicator_config_reconciliations",
        column_name="source_record_ids",
        udt_name="jsonb",
        nullable=False,
    ),
    RequiredColumn(
        table_name="finn_v2_indicator_config_reconciliations",
        column_name="legacy_config_json",
        udt_name="jsonb",
        nullable=False,
        default_fragment="'{}'::jsonb",
    ),
    RequiredColumn(
        table_name="finn_v2_indicator_config_reconciliations",
        column_name="status",
        udt_name="text",
        nullable=False,
        default_fragment="'asset_scope_required'",
    ),
)


class FinnV2SchemaHealthError(RuntimeError):
    """Raised when active FINN V2 code cannot safely run against the database."""


def _column_metadata(cursor: Any, required: RequiredColumn) -> Optional[tuple[str, str, str, Optional[str]]]:
    cursor.execute(
        """
        SELECT data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        """,
        (required.table_name, required.column_name),
    )
    return cursor.fetchone()


def assert_finn_v2_schema(connection: Any) -> None:
    """Validate the minimum schema contract required before starting FINN V2."""
    with connection.cursor() as cursor:
        for required in REQUIRED_FINN_V2_COLUMNS:
            metadata = _column_metadata(cursor, required)
            if metadata is None:
                raise FinnV2SchemaHealthError(
                    f"finn_v2_schema_missing_column:{required.table_name}.{required.column_name}"
                )

            _data_type, udt_name, is_nullable, column_default = metadata
            if udt_name != required.udt_name:
                raise FinnV2SchemaHealthError(
                    f"finn_v2_schema_invalid_type:{required.table_name}.{required.column_name}:{udt_name}"
                )
            if (is_nullable == "YES") != required.nullable:
                raise FinnV2SchemaHealthError(
                    f"finn_v2_schema_invalid_nullability:{required.table_name}.{required.column_name}:{is_nullable}"
                )
            if required.default_fragment and required.default_fragment not in (column_default or ""):
                raise FinnV2SchemaHealthError(
                    f"finn_v2_schema_invalid_default:{required.table_name}.{required.column_name}"
                )

        # This read catches permissions or a malformed relation before PM2 starts.
        cursor.execute("SELECT context_json FROM finn_v2_conversations LIMIT 1")
        cursor.fetchone()
        cursor.execute("SELECT information_scope FROM finn_v2_evidence_artifacts LIMIT 1")
        cursor.fetchone()
        cursor.execute(
            "SELECT operation_id, operation_contract_version FROM finn_v2_tool_calls LIMIT 1"
        )
        cursor.fetchone()
        cursor.execute(
            "SELECT operation_id, operation_contract_version FROM finn_v2_evidence_artifacts LIMIT 1"
        )
        cursor.fetchone()
        cursor.execute(
            "SELECT user_id, symbol, category, indicator, provenance, source_record_id "
            "FROM user_indicator_configs LIMIT 1"
        )
        cursor.fetchone()
        cursor.execute(
            "SELECT source_user_id, category, indicator, status "
            "FROM finn_v2_indicator_config_reconciliations LIMIT 1"
        )
        cursor.fetchone()

        # A legacy user selection may only be present when it is traceable in
        # reconciliation. This blocks releases that point runtime reads at an
        # empty canonical table while silently abandoning old user data.
        for table_name in (
            "technical_indicator_rules",
            "market_indicator_rules",
            "macro_indicator_rules",
        ):
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {table_name} AS legacy
                WHERE legacy.user_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM finn_v2_indicator_config_reconciliations AS reconciliation
                    WHERE reconciliation.source_table = %s
                      AND reconciliation.source_user_id = legacy.user_id
                      AND reconciliation.source_record_ids @> jsonb_build_array(legacy.id)
                  )
                """,
                (table_name,),
            )
            unresolved = cursor.fetchone()
            if unresolved and int(unresolved[0] or 0) > 0:
                raise FinnV2SchemaHealthError(
                    f"finn_v2_indicator_cutover_unreconciled_legacy_rows:{table_name}:{unresolved[0]}"
                )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM user_indicator_configs AS legacy
            WHERE legacy.symbol IS NULL
              AND NOT EXISTS (
                SELECT 1
                FROM finn_v2_indicator_config_reconciliations AS reconciliation
                WHERE reconciliation.source_table = 'user_indicator_configs'
                  AND reconciliation.source_user_id = legacy.user_id
                  AND reconciliation.source_record_ids @> jsonb_build_array(legacy.id)
              )
            """
        )
        unresolved = cursor.fetchone()
        if unresolved and int(unresolved[0] or 0) > 0:
            raise FinnV2SchemaHealthError(
                "finn_v2_indicator_cutover_unreconciled_legacy_rows:user_indicator_configs:"
                f"{unresolved[0]}"
            )


def main() -> None:
    connection = get_db_connection()
    if connection is None:
        raise FinnV2SchemaHealthError("finn_v2_schema_database_unavailable")

    try:
        assert_finn_v2_schema(connection)
    finally:
        connection.close()

    logger.info("FINN V2 schema health gate passed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    try:
        main()
    except FinnV2SchemaHealthError as exc:
        logger.error("FINN V2 schema health gate failed: %s", exc)
        sys.exit(1)
