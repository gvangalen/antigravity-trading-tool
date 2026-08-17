from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from typing import Any

from backend.services.platform_metrics import increment_execution_safety_counter


class FinnV2StateRedactionService:
    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        if is_dataclass(value):
            return self._json_safe(asdict(value))
        if hasattr(value, "model_dump"):
            return self._json_safe(value.model_dump(by_alias=True))
        if hasattr(value, "dict"):
            return self._json_safe(value.dict(by_alias=True))
        if hasattr(value, "__dict__"):
            return self._json_safe(vars(value))
        return str(value)

    def payload_to_jsonable(self, payload: Any) -> Any:
        if payload is None:
            return None
        if hasattr(payload, "dict"):
            return self._json_safe(payload.dict(by_alias=True))
        if hasattr(payload, "model_dump"):
            return self._json_safe(payload.model_dump(by_alias=True))
        return self._json_safe(deepcopy(payload))

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
