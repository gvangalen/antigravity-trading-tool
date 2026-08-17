from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio

from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService


def _artifact(user_id, tool_name, artifact_id, asset=None, entity_id=None, payload_json=None):
    schema_name_map = {
        "read_active_asset": "ActiveAssetData",
    }
    return SimpleNamespace(
        id=artifact_id,
        run_id=f"run-{user_id}",
        user_id=user_id,
        tool_call_id=int(artifact_id[-1]),
        tool_name=tool_name,
        entity_type=tool_name,
        entity_id=entity_id,
        asset=asset,
        source="internal",
        resolution_source="selected_asset",
        user_scoped=True,
        source_as_of=None,
        freshness="fresh",
        schema_name=schema_name_map[tool_name],
        schema_version="2026-08-17.block3",
        content_hash=f"hash-{artifact_id}",
        payload_json=payload_json or {},
        availability="available",
        error_codes_json=[],
        created_at=datetime.now(timezone.utc),
        redacted_at=None,
    )


class _ArtifactsRepo:
    def __init__(self, rows):
        self.rows = rows

    async def list_for_run(self, *, run_id, user_id):
        return [row for row in self.rows if row.run_id == run_id and row.user_id == user_id]


class _SnapshotsRepo:
    async def get_by_evidence_hash(self, **_kwargs):
        return None

    async def next_revision(self, **_kwargs):
        return 1

    async def create(self, **kwargs):
        return kwargs


def test_financial_chain_keeps_btc_and_aapl_artifacts_isolated():
    rows = [
        _artifact(7, "read_active_asset", "a1", asset="BTC", entity_id="BTC", payload_json={"symbol": "BTC"}),
        _artifact(8, "read_active_asset", "b1", asset="AAPL", entity_id="AAPL", payload_json={"symbol": "AAPL"}),
    ]
    service = FinnV2StateAssemblyService(session=object())
    service.artifacts = _ArtifactsRepo(rows)
    service.snapshots = _SnapshotsRepo()

    btc = asyncio.run(service.assemble_for_run(run_id="run-7", user_id=7))
    aapl = asyncio.run(service.assemble_for_run(run_id="run-8", user_id=8))

    assert any(node.asset == "BTC" for node in btc.nodes)
    assert all(node.asset != "BTC" for node in aapl.nodes if node.asset)
