from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import ActiveSetupData


class SetupToolAdapter:
    async def execute(self, *, setup: dict, resolution_source: str, **_kwargs):
        payload = ActiveSetupData(
            setup_id=setup.get("setup_id") or setup.get("id"),
            name=setup.get("name"),
            symbol=setup.get("symbol"),
            timeframe=setup.get("timeframe"),
            score=float(setup.get("score") or 0) if setup.get("score") is not None else None,
        )
        return {
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
