"""Run one explicitly enabled, non-mutating FINN selector provider canary."""
from __future__ import annotations

import json
import os
import sys

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_structured_operation_selector_service import (
    FinnV2StructuredOperationSelectorService,
)
from backend.utils import openai_client


def main() -> int:
    if os.getenv("FINN_V2_REAL_PROVIDER_CANARY") != "1":
        print(json.dumps({"status": "not_run", "reason": "FINN_V2_REAL_PROVIDER_CANARY_not_enabled"}))
        return 2

    provider_result: dict[str, object] = {}

    def provider(**kwargs):
        result = openai_client.ask_gpt_structured_response(**kwargs)
        provider_result.update(result)
        return result

    selection, error = FinnV2StructuredOperationSelectorService(provider=provider).select(
        message="Wat betekent RSI?",
        candidate_contracts=FinnV2OperationRegistry().list(),
        facts={
            "entities": (),
            "action_polarity": "read",
            "discourse_act": "information_request",
            "financial_concept": "RSI",
            "domain_hint": "financial",
        },
        verified_context=None,
    )
    entities = dict(selection.entities) if selection is not None else {}
    passed = bool(
        not error
        and selection is not None
        and selection.operation_id == "explain_financial_concept"
        and selection.confidence >= 0
        and entities.get("concept") == "RSI"
    )
    print(json.dumps({
        "status": "passed" if passed else "failed",
        "provider_status": (provider_result.get("provider_metadata") or {}).get("response_status"),
        "parsed": bool(provider_result.get("parsed")),
        "operation_id": selection.operation_id if selection else None,
        "has_confidence": bool(selection is not None),
        "concept": entities.get("concept"),
        "error": error,
    }))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
