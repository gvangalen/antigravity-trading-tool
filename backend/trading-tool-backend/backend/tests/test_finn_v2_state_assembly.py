from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio

from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService


def _artifact(tool_name, artifact_id, tool_call_id, payload_json, availability="available", asset=None, entity_id=None):
    schema_name_map = {
        "read_profile": "TraderProfileData",
        "read_user_preferences": "UserPreferencesData",
        "read_active_asset": "ActiveAssetData",
    }
    return SimpleNamespace(
        id=artifact_id,
        run_id="run-1",
        user_id=7,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        entity_type=tool_name.replace("read_", ""),
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
        payload_json=payload_json,
        availability=availability,
        error_codes_json=[],
        created_at=datetime.now(timezone.utc),
        redacted_at=None,
    )


class _ArtifactsRepo:
    async def list_for_run(self, *, run_id, user_id):
        return [
            _artifact("read_profile", "a1", 1, {"trader_profile": {"trader_types": ["investor"]}, "has_profile": True}),
            _artifact("read_user_preferences", "a2", 2, {"selected_asset": "BTC"}),
            _artifact("read_active_asset", "a3", 3, {"symbol": "BTC"}, asset="BTC", entity_id="BTC"),
        ]


class _SnapshotsRepo:
    async def get_by_evidence_hash(self, **_kwargs):
        return None

    async def next_revision(self, **_kwargs):
        return 1

    async def create(self, **kwargs):
        return SimpleNamespace(**kwargs)


def test_state_assembly_uses_only_evidence_artifacts():
    service = FinnV2StateAssemblyService(session=object())
    service.artifacts = _ArtifactsRepo()
    service.snapshots = _SnapshotsRepo()

    snapshot = asyncio.run(service.assemble_for_run(run_id="run-1", user_id=7))

    assert snapshot.run_id == "run-1"
    assert any(node.node_id == "profile" for node in snapshot.nodes)
