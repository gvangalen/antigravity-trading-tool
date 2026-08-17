from datetime import datetime, timezone

from backend.schemas.finn_v2_evidence_schema import EvidenceArtifact, TraderProfileData


def test_evidence_schema_accepts_typed_payload():
    artifact = EvidenceArtifact(
        artifact_id="artifact-1",
        run_id="run-1",
        user_id=7,
        tool_call_id=11,
        tool_name="read_profile",
        source="users.ai_preferences",
        resolution_source="selected_asset",
        user_scoped=True,
        freshness="not_applicable",
        schema_name="TraderProfileData",
        schema_version="2026-08-17.block3",
        content_hash="abc",
        payload=TraderProfileData(trader_profile={"trader_types": ["investor"]}, has_profile=True),
        availability="available",
        created_at=datetime.now(timezone.utc),
    )

    assert artifact.payload.has_profile is True

