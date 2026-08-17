from datetime import datetime, timezone

from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot


def test_state_schema_accepts_empty_snapshot():
    snapshot = FinancialStateSnapshot(
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        revision=1,
        evidence_set_hash="abc",
        assembled_at=datetime.now(timezone.utc),
    )

    assert snapshot.revision == 1

