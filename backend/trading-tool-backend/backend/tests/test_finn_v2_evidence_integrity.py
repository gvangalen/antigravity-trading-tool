from types import SimpleNamespace
import asyncio

import pytest

from backend.schemas.finn_v2_evidence_schema import TraderProfileData
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope
from backend.services.finn_v2_evidence_ingestion_service import FinnV2EvidenceIngestionService


def test_evidence_hash_is_deterministic_and_changes_on_payload_change():
    service = FinnV2EvidenceIngestionService(session=object())
    first = ToolExecutionEnvelope(tool_name="read_profile", status="completed", success=True, result=TraderProfileData(trader_profile={"trader_types": ["investor"]}, has_profile=True), schema_name="TraderProfileData")
    second = ToolExecutionEnvelope(tool_name="read_profile", status="completed", success=True, result=TraderProfileData(trader_profile={"trader_types": ["investor"]}, has_profile=True), schema_name="TraderProfileData")
    third = ToolExecutionEnvelope(tool_name="read_profile", status="completed", success=True, result=TraderProfileData(trader_profile={"trader_types": ["swing_trader"]}, has_profile=True), schema_name="TraderProfileData")

    assert service._content_hash(first) == service._content_hash(second)
    assert service._content_hash(first) != service._content_hash(third)


def test_duplicate_conflicting_artifact_is_rejected():
    service = FinnV2EvidenceIngestionService(session=object())
    service.runs = SimpleNamespace(get_by_id_for_user=lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-1", user_id=7)))
    service.tool_calls = SimpleNamespace(get_by_id=lambda _tool_call_id: asyncio.sleep(0, result=SimpleNamespace(id=11, run_id="run-1", user_id=7, tool_name="read_profile")))
    service.artifacts = SimpleNamespace(
        get_by_tool_call_id=lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(content_hash="other", id="artifact-1", run_id="run-1", user_id=7, tool_call_id=11, tool_name="read_profile", entity_type=None, entity_id=None, asset=None, source="x", resolution_source="x", user_scoped=True, source_as_of=None, freshness="not_applicable", schema_name="TraderProfileData", schema_version="2026-08-17.block3", payload_json=None, availability="available", error_codes_json=[], created_at=None, redacted_at=None))
    )

    envelope = ToolExecutionEnvelope(tool_name="read_profile", status="completed", success=True, result=TraderProfileData(trader_profile={"trader_types": ["investor"]}, has_profile=True), schema_name="TraderProfileData")

    with pytest.raises(ValueError) as exc:
        asyncio.run(service.ingest_tool_result(user_id=7, run_id="run-1", trace_id="trace-1", tool_call_id=11, result=envelope))

    assert str(exc.value) == "artifact_duplicate_conflict"

