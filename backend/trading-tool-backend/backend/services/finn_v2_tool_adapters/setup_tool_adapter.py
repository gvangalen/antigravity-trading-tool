from __future__ import annotations


class SetupToolAdapter:
    async def execute(self, *, setup: dict, resolution_source: str, **_kwargs):
        payload = {
            "setup_id": setup.get("setup_id") or setup.get("id"),
            "name": setup.get("name"),
            "symbol": setup.get("symbol"),
            "timeframe": setup.get("timeframe"),
            "score": float(setup.get("score") or 0) if setup.get("score") is not None else None,
        }
        return {"data": payload, "summary": {"title": "active_setup", "setup_id": payload["setup_id"], "symbol": payload["symbol"]}, "as_of": None, "resolution_source": resolution_source}

