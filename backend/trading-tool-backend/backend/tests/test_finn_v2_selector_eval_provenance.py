from pathlib import Path

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.scripts.run_finn_v2_selector_eval import fixture_paths, provenance_for


def test_selector_eval_provenance_binds_report_to_the_selected_dataset_and_registry():
    provenance = provenance_for(
        dataset="regression", paths=fixture_paths(), registry=FinnV2OperationRegistry()
    )

    assert len(provenance["dataset_sha256"]) == 64
    assert len(provenance["registry_sha256"]) == 64
    assert provenance["registry_version"] == FinnV2OperationRegistry.VERSION
