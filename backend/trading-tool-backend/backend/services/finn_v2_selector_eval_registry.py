"""Versioned, data-only registry for direct FINN selector evaluations."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.domain.finn_v2_operation_registry import ActionPolarity, FinnV2OperationRegistry


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
    expected_action_polarity: ActionPolarity | None = None
    expected_conversation_reference: str | None = None
    expected_clarification: bool = False
    # Every case must declare this explicitly. An empty list is meaningful;
    # omission is a dataset contract error rather than an implicit default.
    expected_missing_inputs: list[str] = Field(...)
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

MIGRATION_FILENAME = "finn_v2_selector_fixture_migrations.json"


def _fixture_migrations(paths: list[Path]) -> dict[str, dict[str, Any]]:
    migrations: dict[str, dict[str, Any]] = {}
    # The governed migration belongs to the published holdout source. Looking
    # beside development/regression fixtures would make temporary test copies
    # accidentally load two manifests for the same sealed cases.
    for directory in {path.parent for path in paths if path.name == "finn_v2_selector_holdout.json"}:
        migration_path = directory / MIGRATION_FILENAME
        if not migration_path.exists():
            continue
        payload = json.loads(migration_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("migrations"), list):
            raise ValueError(f"fixture_migration_manifest_invalid:{migration_path}")
        for migration in payload["migrations"]:
            if not isinstance(migration, dict) or not isinstance(migration.get("eval_id"), str):
                raise ValueError(f"fixture_migration_entry_invalid:{migration_path}")
            eval_id = migration["eval_id"]
            if eval_id in migrations:
                raise ValueError(f"duplicate_fixture_migration:{eval_id}")
            migrations[eval_id] = migration
    return migrations


def _validate_fixture_migration(*, case: SelectorEvalCase, contract: Any, migration: dict[str, Any]) -> None:
    if migration.get("dataset") != case.dataset or migration.get("expected_operation_id") != case.expected_operation_id:
        raise ValueError(f"fixture_migration_contract_mismatch:{case.eval_id}")
    expected_hash = hashlib.sha256(case.input_query.encode("utf-8")).hexdigest()
    if migration.get("input_query_sha256") != expected_hash:
        raise ValueError(f"fixture_migration_prompt_mismatch:{case.eval_id}")
    original = migration.get("original_expected_missing_inputs")
    supplied = migration.get("supplied_input_fields")
    if not isinstance(original, list) or not isinstance(supplied, list):
        raise ValueError(f"fixture_migration_inputs_invalid:{case.eval_id}")
    if any(field not in contract.required_inputs for field in supplied):
        raise ValueError(f"fixture_migration_unknown_supplied_input:{case.eval_id}")
    derived = [field for field in contract.required_inputs if field not in supplied]
    if migration.get("derived_expected_missing_inputs") != derived:
        raise ValueError(f"fixture_migration_not_registry_derived:{case.eval_id}")
    if case.expected_missing_inputs != derived:
        raise ValueError(f"fixture_migration_case_not_derived:{case.eval_id}")
    if original == derived:
        raise ValueError(f"fixture_migration_no_effect:{case.eval_id}")


def load_and_validate(paths: list[Path]) -> list[SelectorEvalCase]:
    registry = FinnV2OperationRegistry()
    migrations = _fixture_migrations(paths)
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
            if (
                case.expected_action_polarity is not None
                and case.expected_action_polarity != contract.action_polarity
            ):
                raise ValueError(
                    f"canonical_action_polarity_mismatch:{case.eval_id}:"
                    f"{case.expected_action_polarity.value}!={contract.action_polarity.value}"
                )
            if contract.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"} and case.expected_supported and not contract.execution_adapter:
                raise ValueError(f"non_executable_write_expected:{case.eval_id}")
            migration = migrations.pop(case.eval_id, None)
            if migration is not None:
                _validate_fixture_migration(case=case, contract=contract, migration=migration)
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
    if migrations:
        raise ValueError(f"fixture_migration_case_missing:{sorted(migrations)}")
    return cases
