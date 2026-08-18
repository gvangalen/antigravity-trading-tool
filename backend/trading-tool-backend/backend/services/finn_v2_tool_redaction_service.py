from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from typing import Any, Dict


class FinnV2ToolRedactionService:
    def redact_selector(self, selector: Dict[str, Any]) -> Dict[str, Any]:
        return self._shrink_payload(self._json_safe(selector or {}), 8192)

    def redact_result_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        redacted = deepcopy(self._json_safe(payload or {}))
        for key in list(redacted.keys()):
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "password", "holding", "positions", "wallet")):
                redacted[key] = "[redacted]"
        return self._shrink_payload(redacted, 65536)

    def _shrink_payload(self, payload: Dict[str, Any], max_bytes: int) -> Dict[str, Any]:
        candidate = deepcopy(payload)
        raw = json.dumps(candidate, default=str).encode("utf-8")
        if len(raw) <= max_bytes:
            return candidate
        trimmed: Dict[str, Any] = {}
        for key, value in candidate.items():
            if isinstance(value, list):
                trimmed[key] = value[:5]
            elif isinstance(value, dict):
                trimmed[key] = {inner_key: value[inner_key] for inner_key in list(value.keys())[:8]}
            else:
                trimmed[key] = value
        raw = json.dumps(trimmed, default=str).encode("utf-8")
        if len(raw) <= max_bytes:
            return trimmed
        return {"status": "truncated", "keys": list(trimmed.keys())[:12]}

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
            return self._json_safe(value.dict())
        if hasattr(value, "__dict__"):
            return {
                str(key): self._json_safe(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }
        return str(value)
