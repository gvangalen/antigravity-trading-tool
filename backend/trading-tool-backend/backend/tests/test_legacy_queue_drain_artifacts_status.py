import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
LATEST_ARTIFACT = (
    REPO_ROOT
    / "ops"
    / "queue-drain-artifacts"
    / "legacy-queue-drain-celery-apply-20260525T121201Z.json"
)


def test_latest_legacy_queue_drain_artifact_is_bounded_and_clean():
    payload = json.loads(LATEST_ARTIFACT.read_text())
    summary = payload["operator_summary"]

    assert payload["apply"] is True
    assert summary["processed"] == 1500
    assert summary["rerouted"] == 1500
    assert summary["kept"] == 0
    assert summary["reroute_ratio_before"] == 1.0
    assert summary["reroute_ratio_after"] == 1.0
    assert summary["stop_reason"] == "max_processed_total_reached"


def test_queue_drain_docs_reference_latest_artifact():
    runbook = (REPO_ROOT / "docs" / "operations" / "legacy-celery-queue-drain.md").read_text()
    status = (REPO_ROOT / "docs" / "operations" / "platform-hardening-status.md").read_text()

    assert LATEST_ARTIFACT.name in runbook
    assert "processed `1500`, rerouted `1500`, kept `0`" in status
    assert "Default queue was about `48714`" in status
