from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_evidence_schema import EvidenceArtifact
from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService


def _artifact(tool_name, node_payload, artifact_id, asset=None, entity_id=None):
    schema_name_map = {
        "read_profile": "TraderProfileData",
        "read_user_preferences": "UserPreferencesData",
        "read_active_asset": "ActiveAssetData",
    }
    return EvidenceArtifact(
        artifact_id=artifact_id,
        run_id="run-1",
        user_id=7,
        tool_call_id=int(artifact_id[-1]),
        tool_name=tool_name,
        entity_type=tool_name,
        entity_id=entity_id,
        asset=asset,
        source="internal",
        resolution_source="selected_asset",
        user_scoped=True,
        freshness="fresh",
        schema_name=schema_name_map[tool_name],
        schema_version="2026-08-17.block3",
        content_hash=f"hash-{artifact_id}",
        payload=node_payload,
        availability="available",
        created_at=datetime.now(timezone.utc),
    )


def test_state_edges_only_exist_when_both_nodes_exist():
    service = FinnV2StateAssemblyService(session=object())
    artifacts = [
        _artifact("read_profile", {"trader_profile": {}, "has_profile": True}, "a1"),
        _artifact("read_user_preferences", {"selected_asset": "BTC"}, "a2"),
        _artifact("read_active_asset", {"symbol": "BTC"}, "a3", asset="BTC", entity_id="BTC"),
    ]

    nodes = service._build_nodes(artifacts)
    edges = service._build_edges(nodes)

    assert any(edge.relation == "has_preferences" for edge in edges)
    assert any(edge.relation == "focuses_on_asset" for edge in edges)
