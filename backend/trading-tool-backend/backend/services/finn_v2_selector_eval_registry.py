"""Versioned, data-only registry for direct FINN selector evaluations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry


class SelectorEvalCase(BaseModel):
    eval_id: str
    dataset: Literal["development", "regression", "holdout"]
    input_query: str
    conversation_context: dict = Field(default_factory=dict)
    expected_operation_id: str
    expected_domain: str
    expected_supported: bool
    expected_entities: dict = Field(default_factory=dict)
    expected_target_asset: str | None = None
    expected_action_polarity: str | None = None
    expected_conversation_reference: str | None = None
    expected_clarification: bool = False
    provider_call_expected: bool = True


REQUIRED_OPERATION_FAMILIES = {
    "capability", "read_active_asset", "read_indicator_configuration",
    "read_active_setup", "read_active_plan", "evaluate_plan",
    "explain_previous_evidence", "reformulate_previous_response", "create_setup",
    "watchlist_add", "watchlist_remove", "activate_bot", "off_topic",
    "unsupported_financial_operation", "clarify_request", "explain_financial_concept",
}

OPERATION_FAMILY = {
    "read_indicator_configuration": "read_indicator_configuration",
    "evaluate_indicator_configuration": "read_indicator_configuration",
}


def load_and_validate(paths: list[Path]) -> list[SelectorEvalCase]:
    registry = FinnV2OperationRegistry()
    cases: list[SelectorEvalCase] = []
    ids: set[str] = set()
    queries: set[str] = set()
    families_by_dataset: dict[str, set[str]] = {
        "development": set(), "regression": set(), "holdout": set(),
    }
    holdout_queries: list[str] = []
    for path in paths:
        for raw in json.loads(path.read_text(encoding="utf-8")):
            case = SelectorEvalCase.parse_obj(raw)
            if case.eval_id in ids:
                raise ValueError(f"duplicate_eval_id:{case.eval_id}")
            normalized = case.input_query.casefold().strip()
            if normalized in queries:
                raise ValueError(f"duplicate_query:{case.eval_id}")
            if path.stem.split("_")[-1] != case.dataset:
                raise ValueError(f"dataset_filename_mismatch:{case.eval_id}")
            contract = registry.get(case.expected_operation_id)
            if contract.domain != case.expected_domain or contract.supported != case.expected_supported:
                raise ValueError(f"contract_expectation_mismatch:{case.eval_id}")
            if contract.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"} and case.expected_supported and not contract.execution_adapter:
                raise ValueError(f"non_executable_write_expected:{case.eval_id}")
            ids.add(case.eval_id)
            queries.add(normalized)
            families_by_dataset[case.dataset].add(
                OPERATION_FAMILY.get(case.expected_operation_id, case.expected_operation_id)
            )
            cases.append(case)
            if case.dataset == "holdout":
                holdout_queries.append(normalized)
    for dataset, families in families_by_dataset.items():
        missing = REQUIRED_OPERATION_FAMILIES.difference(families)
        if missing:
            raise ValueError(f"required_operation_coverage_missing:{dataset}:{sorted(missing)}")
    prompt_examples = {
        example.casefold().strip()
        for contract in registry.list()
        for example in (*contract.aliases, *contract.positive_examples, *contract.negative_examples)
    }
    leaked = sorted(set(holdout_queries).intersection(prompt_examples))
    if leaked:
        raise ValueError(f"holdout_prompt_leakage:{leaked}")
    return cases
