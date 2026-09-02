"""Versioned, data-only registry for direct FINN selector evaluations."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Literal, Mapping

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
PUBLISHED_REGRESSION_KIND = "published_frozen_regression"


def _fixture_migrations(paths: list[Path]) -> dict[str, dict[str, Any]]:
    migrations: dict[str, dict[str, Any]] = {}
    # A published source can be projected into regression without carrying a
    # ``*_holdout.json`` filename. Ordinary development/regression files do
    # not opt into a neighboring holdout migration manifest.
    directories = {path.parent for path in paths if path.name == "finn_v2_selector_holdout.json"}
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("kind") == PUBLISHED_REGRESSION_KIND:
            directories.add(path.parent)
    for directory in directories:
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


def _raw_cases_for_path(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Load ordinary cases or an immutable published-holdout projection.

    A published holdout is never rewritten: its source bytes and hash remain
    authoritative.  The registry only projects it into the regression lane
    after explicit publication, preventing it from being presented as an
    independent holdout again.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, False
    if not isinstance(payload, dict) or payload.get("kind") != PUBLISHED_REGRESSION_KIND:
        raise ValueError(f"fixture_payload_invalid:{path}")
    source_name = payload.get("source_file")
    expected_hash = payload.get("source_sha256")
    if not isinstance(source_name, str) or not isinstance(expected_hash, str):
        raise ValueError(f"published_regression_manifest_invalid:{path}")
    source_path = path.parent / source_name
    source_bytes = source_path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != expected_hash:
        raise ValueError(f"published_regression_source_hash_mismatch:{path}")
    source_payload = json.loads(source_bytes)
    raw_cases = source_payload.get("cases") if isinstance(source_payload, dict) else source_payload
    if not isinstance(raw_cases, list) or not all(isinstance(item, dict) for item in raw_cases):
        raise ValueError(f"published_regression_source_invalid:{path}")
    errata = _load_errata(payload=payload, path=path, source_bytes=source_bytes)
    cases = []
    for source_case in raw_cases:
        case = dict(source_case)
        correction = errata.get(str(case.get("eval_id") or ""))
        if correction is not None:
            field, old_value, canonical_value = correction
            if case.get(field) != old_value:
                raise ValueError(f"corpus_erratum_source_value_mismatch:{case.get('eval_id')}:{field}")
            case[field] = canonical_value
        # Dataset assignment is a runner projection only. The frozen source
        # remains byte-for-byte intact and records its original dataset.
        case["dataset"] = "regression"
        case["provider_call_expected"] = True
        cases.append(case)
    return cases, True


def _registry_hash() -> str:
    registry = FinnV2OperationRegistry()
    manifest = [contract.__dict__ for contract in registry.list()]
    return hashlib.sha256(
        json.dumps(manifest, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_errata(*, payload: Mapping[str, Any], path: Path, source_bytes: bytes) -> dict[str, tuple[str, object, object]]:
    """Apply only registry-bound corpus errata to a regression projection."""
    errata_file = payload.get("errata_file")
    if errata_file is None:
        return {}
    if not isinstance(errata_file, str):
        raise ValueError(f"corpus_errata_manifest_invalid:{path}")
    errata_path = path.parent / errata_file
    errata_payload = json.loads(errata_path.read_text(encoding="utf-8"))
    if not isinstance(errata_payload, Mapping) or errata_payload.get("kind") != "registry_bound_corpus_errata":
        raise ValueError(f"corpus_errata_manifest_invalid:{errata_path}")
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if errata_payload.get("source_file") != payload.get("source_file") or errata_payload.get("source_sha256") != source_hash:
        raise ValueError(f"corpus_errata_provenance_mismatch:{errata_path}")
    registry = FinnV2OperationRegistry()
    if (
        errata_payload.get("registry_version") != registry.VERSION
        or errata_payload.get("registry_sha256") != _registry_hash()
    ):
        raise ValueError(f"corpus_errata_registry_mismatch:{errata_path}")
    entries = errata_payload.get("errata")
    if not isinstance(entries, list):
        raise ValueError(f"corpus_errata_entries_invalid:{errata_path}")
    corrections: dict[str, tuple[str, object, object]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError(f"corpus_errata_entry_invalid:{errata_path}")
        eval_id = entry.get("eval_id")
        field = entry.get("field")
        if not isinstance(eval_id, str) or field != "expected_supported" or eval_id in corrections:
            raise ValueError(f"corpus_errata_entry_invalid:{errata_path}")
        old_value = entry.get("old_value")
        canonical_value = entry.get("canonical_value")
        if not isinstance(old_value, bool) or not isinstance(canonical_value, bool):
            raise ValueError(f"corpus_errata_value_invalid:{eval_id}")
        contract = registry.get(_source_operation_id(path.parent / str(payload["source_file"]), eval_id))
        if canonical_value != contract.supported:
            raise ValueError(f"corpus_errata_not_registry_derived:{eval_id}")
        corrections[eval_id] = (field, old_value, canonical_value)
    return corrections


def _source_operation_id(source_path: Path, eval_id: str) -> str:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, Mapping) else payload
    if not isinstance(cases, list):
        raise ValueError(f"corpus_errata_source_invalid:{source_path}")
    for case in cases:
        if isinstance(case, Mapping) and case.get("eval_id") == eval_id and isinstance(case.get("expected_operation_id"), str):
            return case["expected_operation_id"]
    raise ValueError(f"corpus_errata_case_missing:{eval_id}")


def load_and_validate(
    paths: list[Path], *, allow_published_regression: bool = False,
) -> list[SelectorEvalCase]:
    registry = FinnV2OperationRegistry()
    migrations = _fixture_migrations(paths)
    cases: list[SelectorEvalCase] = []
    ids: set[str] = set()
    queries: set[str] = set()
    families_by_dataset: dict[str, set[str]] = {
        "development": set(), "regression": set(), "holdout": set(),
    }
    holdout_queries: list[str] = []
    has_published_regression = False
    for path in paths:
        raw_cases, published = _raw_cases_for_path(path)
        has_published_regression = has_published_regression or published
        if published and not allow_published_regression:
            raise ValueError("published_holdout_requires_explicit_regression_mode")
        for raw in raw_cases:
            case = SelectorEvalCase.parse_obj(raw)
            if case.eval_id in ids:
                raise ValueError(f"duplicate_eval_id:{case.eval_id}")
            normalized = case.input_query.casefold().strip()
            if normalized in queries:
                raise ValueError(f"duplicate_query:{case.eval_id}")
            if not published and path.stem.split("_")[-1] != case.dataset:
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
                if published:
                    # The source migration predates publication. Its prompt
                    # and registry-derived slots stay identical; only the
                    # runner lane changes from holdout to regression.
                    migration = {**migration, "dataset": case.dataset}
                _validate_fixture_migration(case=case, contract=contract, migration=migration)
            ids.add(case.eval_id)
            queries.add(normalized)
            families_by_dataset[case.dataset].add(
                OPERATION_FAMILY.get(case.expected_operation_id, case.expected_operation_id)
            )
            cases.append(case)
            if case.dataset == "holdout":
                holdout_queries.append(normalized)
    required_datasets = {"development", "regression"}
    if not has_published_regression:
        required_datasets.add("holdout")
    for dataset in required_datasets:
        families = families_by_dataset[dataset]
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
