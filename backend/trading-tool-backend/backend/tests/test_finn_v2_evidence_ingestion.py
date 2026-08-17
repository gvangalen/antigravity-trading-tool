from types import SimpleNamespace
import asyncio

from backend.schemas.finn_v2_evidence_schema import TraderProfileData
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope
from backend.services.finn_v2_evidence_ingestion_service import FinnV2EvidenceIngestionService


class _RunRepo:
    async def get_by_id_for_user(self, *, run_id, user_id):
        return SimpleNamespace(id=run_id, user_id=user_id)


class _ToolCallRepo:
    async def get_by_id(self, tool_call_id):
        return SimpleNamespace(id=tool_call_id, run_id="run-1", user_id=7, tool_name="read_profile")


class _ArtifactsRepo:
    def __init__(self):
        self.created = []

    async def get_by_tool_call_id(self, *, tool_call_id, user_id):
        return None

    async def create(self, **kwargs):
        row = SimpleNamespace(created_at=kwargs.get("created_at"), redacted_at=None, **kwargs)
        self.created.append(row)
        return row


def test_evidence_ingestion_creates_artifact_from_typed_tool_output():
    service = FinnV2EvidenceIngestionService(session=object())
    service.runs = _RunRepo()
    service.tool_calls = _ToolCallRepo()
    service.artifacts = _ArtifactsRepo()

    envelope = ToolExecutionEnvelope(
        tool_name="read_profile",
        status="completed",
        success=True,
        result=TraderProfileData(trader_profile={"trader_types": ["investor"]}, has_profile=True),
        source="users.ai_preferences",
        schema_name="TraderProfileData",
        availability="available",
        entity_type="profile",
    )

    artifact = asyncio.run(
        service.ingest_tool_result(
            user_id=7,
            run_id="run-1",
            trace_id="trace-1",
            tool_call_id=11,
            result=envelope,
        )
    )

    assert artifact.tool_name == "read_profile"
    assert artifact.availability == "available"

