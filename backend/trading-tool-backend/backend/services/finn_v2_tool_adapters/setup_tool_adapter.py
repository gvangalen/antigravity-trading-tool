from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import ActiveSetupData


class SetupToolAdapter:
    async def execute(self, *, setup: dict, resolution_source: str, setups=None, **_kwargs):
        collection = [
            {
                "setup_id": row.get("setup_id") or row.get("id"),
                "name": row.get("name"),
                "symbol": row.get("symbol"),
                "timeframe": row.get("timeframe"),
                "setup_type": row.get("setup_type"),
                "dca_frequency": row.get("dca_frequency"),
                "dca_day": row.get("dca_day"),
                "dca_month_day": row.get("dca_month_day"),
                "min_investment": row.get("min_investment"),
            }
            for row in (setups or [])
        ]
        payload = ActiveSetupData(
            setup_id=setup.get("setup_id") or setup.get("id"),
            name=setup.get("name"),
            symbol=setup.get("symbol"),
            timeframe=setup.get("timeframe"),
            setup_type=setup.get("setup_type"),
            dca_frequency=setup.get("dca_frequency"),
            dca_day=setup.get("dca_day"),
            dca_month_day=setup.get("dca_month_day"),
            min_investment=setup.get("min_investment"),
            score=float(setup.get("score") or 0) if setup.get("score") is not None else None,
            setups=collection,
            setup_count=len(collection) if collection else None,
        )
        result = {
            "data": payload,
            "summary": {"title": "active_setup", "setup_id": payload.setup_id, "symbol": payload.symbol},
            "as_of": None,
            "resolution_source": resolution_source,
            "source": "setups",
            "schema_name": "ActiveSetupData",
            "entity_type": "setup",
            "entity_id": str(payload.setup_id),
            "asset": payload.symbol,
        }
        return result
