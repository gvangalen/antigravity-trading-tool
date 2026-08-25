import ast
from enum import Enum
from pathlib import Path

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.domain.finn_v2_source_registry import (
    FinnV2CanonicalSourceError,
    FinnV2InformationSourceRegistry,
    SourceClassification,
)


def test_every_operation_scope_has_one_canonical_source():
    source_registry = FinnV2InformationSourceRegistry()
    operation_registry = FinnV2OperationRegistry()

    for contract in operation_registry.list():
        for scope in (*contract.required_scopes, *contract.optional_scopes):
            source = source_registry.get(scope)
            assert source.canonical_repository
            assert source.classification in {
                SourceClassification.CANONICAL_PRODUCT_STATE,
                SourceClassification.DERIVED_VIEW,
                SourceClassification.SYSTEM_DEFINITION,
            }
            assert source.legacy_runtime_access_allowed is False


def test_asset_scoped_source_cache_identity_contains_owner_asset_operation_and_contract():
    source = FinnV2InformationSourceRegistry().get("indicator_configuration")

    key = source.cache_key(
        user_id=406,
        symbol="BTC",
        operation_id="read_indicator_configuration",
        contract_version=1,
    )

    assert key == "indicator_configuration:v2:406:BTC:read_indicator_configuration:1"


def test_asset_scoped_source_rejects_an_incomplete_cache_identity():
    source = FinnV2InformationSourceRegistry().get("indicator_configuration")

    with pytest.raises(FinnV2CanonicalSourceError, match="missing_canonical_asset"):
        source.cache_key(
            user_id=406,
            symbol=None,
            operation_id="read_indicator_configuration",
            contract_version=1,
        )


def test_legacy_indicator_rules_are_not_runtime_user_selection_sources():
    legacy_sources = FinnV2InformationSourceRegistry().legacy_sources()

    assert all(not source.runtime_access_allowed for source in legacy_sources)
    assert {source.table_name for source in legacy_sources} >= {
        "technical_indicator_rules",
        "market_indicator_rules",
        "macro_indicator_rules",
    }


def test_source_classification_keeps_python_310_compatible_string_enum_contract():
    """Celery workers run on Python 3.10, which has no enum.StrEnum."""
    assert issubclass(SourceClassification, str)
    assert issubclass(SourceClassification, Enum)

    registry_source = Path(__file__).parents[1] / "domain" / "finn_v2_source_registry.py"
    tree = ast.parse(registry_source.read_text(encoding="utf-8"))
    source_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SourceClassification"
    )
    assert [base.id for base in source_class.bases if isinstance(base, ast.Name)] == ["str", "Enum"]
