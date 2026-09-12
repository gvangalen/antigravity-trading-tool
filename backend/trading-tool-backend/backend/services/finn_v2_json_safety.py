from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from typing import Any


def to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        # PostgreSQL text/JSON columns reject NUL. Provider output is untrusted
        # transport data, so remove only the non-representable character before
        # persisting the otherwise unchanged structured result.
        return value.replace("\x00", "")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]
    if is_dataclass(value):
        return to_json_safe(asdict(value))
    if hasattr(value, "model_dump"):
        return to_json_safe(value.model_dump(by_alias=True))
    if hasattr(value, "dict"):
        return to_json_safe(value.dict(by_alias=True))
    if hasattr(value, "__dict__"):
        return {
            str(key): to_json_safe(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)
