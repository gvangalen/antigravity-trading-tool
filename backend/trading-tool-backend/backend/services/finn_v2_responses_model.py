"""One model configuration for FINN's Responses chat and bounded helpers."""

from __future__ import annotations

import os
from typing import Any


def finn_responses_model_options() -> dict[str, Any]:
    model = os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna").strip() or "gpt-6-luna"
    if model.startswith("gpt-6-"):
        effort = os.getenv("FINN_RESPONSES_REASONING_EFFORT", "none").strip() or "none"
        return {"model": model, "reasoning": {"effort": effort}}
    return {"model": model, "temperature": 0}


def finn_structured_model_options() -> dict[str, Any]:
    options = finn_responses_model_options()
    return {
        "model_override": options["model"],
        **({"reasoning_effort": options["reasoning"]["effort"]}
           if "reasoning" in options else {}),
    }
