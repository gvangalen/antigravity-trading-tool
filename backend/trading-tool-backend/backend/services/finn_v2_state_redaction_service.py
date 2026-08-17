from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from backend.services.platform_metrics import increment_execution_safety_counter


class FinnV2StateRedactionService:
    def payload_to_jsonable(self, payload: Any) -> Any:
        if payload is None:
            return None
        if hasattr(payload, "dict"):
            return payload.dict(by_alias=True)
        if hasattr(payload, "model_dump"):
            return payload.model_dump(by_alias=True)
        return deepcopy(payload)

    def enforce_max_bytes(self, payload: Any, *, max_bytes: int, label: str) -> Any:
        jsonable = self.payload_to_jsonable(payload)
        raw = json.dumps(jsonable, default=str, sort_keys=True).encode("utf-8")
        if len(raw) <= max_bytes:
            return jsonable
        increment_execution_safety_counter("finn_v2_state_payload_redactions_total")
        increment_execution_safety_counter("payload_redacted")
        if isinstance(jsonable, dict):
            return {
                "redacted": True,
                "label": label,
                "keys": list(jsonable.keys())[:16],
            }
        return {"redacted": True, "label": label}
