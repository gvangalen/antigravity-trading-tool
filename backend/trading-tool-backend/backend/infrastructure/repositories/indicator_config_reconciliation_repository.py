"""Explicit, owner-scoped reconciliation for legacy indicator selections.

Legacy rule tables have no asset identity.  They may never be used as a FINN
runtime fallback; this repository only moves a user-owned legacy group into
the canonical product table after the user supplies an explicit asset.
"""

from __future__ import annotations

from json import loads
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository


class IndicatorConfigReconciliationError(ValueError):
    pass


class IndicatorConfigReconciliationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._canonical = TechnicalDataRepository(session)

    async def list_pending(self, user_id: int) -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                SELECT id, category, indicator, source_record_ids, legacy_config_json,
                       status, created_at
                FROM finn_v2_indicator_config_reconciliations
                WHERE source_user_id = :user_id
                  AND status = 'asset_scope_required'
                ORDER BY category, indicator, id
                """
            ),
            {"user_id": user_id},
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def assign_to_asset(self, *, reconciliation_id: int, user_id: int, symbol: str) -> dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            raise IndicatorConfigReconciliationError("indicator_reconciliation_symbol_required")

        result = await self.session.execute(
            text(
                """
                SELECT id, source_user_id, category, indicator, source_record_ids,
                       legacy_config_json, status, resolved_symbol, canonical_config_id
                FROM finn_v2_indicator_config_reconciliations
                WHERE id = :reconciliation_id
                  AND source_user_id = :user_id
                FOR UPDATE
                """
            ),
            {"reconciliation_id": reconciliation_id, "user_id": user_id},
        )
        row = result.first()
        if row is None:
            raise IndicatorConfigReconciliationError("indicator_reconciliation_not_found")
        item = dict(row._mapping)
        status = str(item["status"])
        if status != "asset_scope_required":
            if str(item.get("resolved_symbol") or "").upper() != normalized_symbol:
                raise IndicatorConfigReconciliationError("indicator_reconciliation_already_resolved")
            return item

        category = str(item["category"]).strip().lower()
        indicator = str(item["indicator"]).strip().lower()
        config = item.get("legacy_config_json") or {}
        if isinstance(config, str):
            config = loads(config)
        source_ids = item.get("source_record_ids") or []
        if isinstance(source_ids, str):
            source_ids = loads(source_ids)
        source_record_id = min((int(value) for value in source_ids), default=None)

        # Existing product state wins: resolving a historic record must never
        # overwrite a more recent asset-scoped choice the user already saved.
        existing = await self._canonical.get_user_configs(
            user_id,
            category=category,
            symbol=normalized_symbol,
        )
        canonical = next(
            (config_row for config_row in existing if str(config_row.indicator).lower() == indicator),
            None,
        )
        if canonical is None:
            canonical = await self._canonical.set_indicator_config_metadata(
                user_id,
                indicator,
                category,
                symbol=normalized_symbol,
                config_json=config,
                priority=int(config.get("priority") or 100),
                provenance="legacy_reconciled",
                source_record_id=source_record_id,
            )
            canonical_rows = await self._canonical.get_user_configs(
                user_id,
                category=category,
                symbol=normalized_symbol,
            )
            canonical = next(
                config_row for config_row in canonical_rows
                if str(config_row.indicator).lower() == indicator
            )

        await self.session.execute(
            text(
                """
                UPDATE finn_v2_indicator_config_reconciliations
                SET status = 'resolved',
                    resolved_symbol = :symbol,
                    canonical_config_id = :canonical_config_id,
                    resolved_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :reconciliation_id
                """
            ),
            {
                "reconciliation_id": reconciliation_id,
                "symbol": normalized_symbol,
                "canonical_config_id": canonical.id,
            },
        )
        await self.session.flush()
        return {
            **item,
            "status": "resolved",
            "resolved_symbol": normalized_symbol,
            "canonical_config_id": canonical.id,
        }
