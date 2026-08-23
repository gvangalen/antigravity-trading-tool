from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_evidence_repository import FinnV2EvidenceRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_tool_call_repository import FinnV2ToolCallRepository
from backend.schemas.finn_v2_evidence_schema import EvidenceArtifact, SCHEMA_VERSION, parse_tool_payload
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_state_redaction_service import FinnV2StateRedactionService


class FinnV2EvidenceIngestionService:
    def __init__(self, session: AsyncSession, flag_service: FinnV2FlagService | None = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.artifacts = FinnV2EvidenceRepository(session)
        self.runs = FinnV2RunRepository(session)
        self.tool_calls = FinnV2ToolCallRepository(session)
        self.redaction = FinnV2StateRedactionService()

    async def ingest_tool_result(
        self,
        *,
        user_id: int,
        run_id: str,
        trace_id: str,
        tool_call_id: int,
        result: ToolExecutionEnvelope,
    ) -> EvidenceArtifact:
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        tool_call = await self.tool_calls.get_by_id(tool_call_id)
        if run is None or tool_call is None:
            raise ValueError("artifact_run_mismatch")
        if tool_call.user_id != user_id:
            raise ValueError("artifact_user_mismatch")
        if tool_call.run_id != run_id:
            raise ValueError("artifact_run_mismatch")
        if tool_call.tool_name != result.tool_name:
            raise ValueError("artifact_schema_invalid")

        existing = await self.artifacts.get_by_tool_call_id(tool_call_id=tool_call_id, user_id=user_id)
        if existing is not None:
            candidate_hash = self._content_hash(result)
            if existing.content_hash != candidate_hash:
                raise ValueError("artifact_duplicate_conflict")
            return self._to_schema(existing)

        payload_json = None
        if result.result is not None:
            payload_json = self.redaction.enforce_max_bytes(
                result.result,
                max_bytes=self.flags.evidence_max_payload_bytes(),
                label=result.tool_name,
            )

        content_hash = self._content_hash(result, payload_override=payload_json)
        source_as_of = self._normalize_datetime(self._extract_source_as_of(result))
        row = await self.artifacts.create(
            id=f"finn-v2-artifact-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            tool_call_id=tool_call_id,
            tool_name=result.tool_name,
            information_scope=result.information_scope.value if result.information_scope else None,
            operation_id=result.operation_id,
            operation_contract_version=result.operation_contract_version,
            entity_type=result.entity_type,
            entity_id=result.entity_id,
            asset=result.asset,
            source=result.source,
            resolution_source=result.resolution_source or "unknown",
            user_scoped=True,
            source_as_of=source_as_of,
            freshness=result.freshness_status or "unknown",
            availability=result.availability,
            schema_name=result.schema_name or result.tool_name,
            schema_version=result.schema_version or SCHEMA_VERSION,
            content_hash=content_hash,
            payload_json=payload_json,
            error_codes_json=list(result.error_codes),
        )
        return self._to_schema(row)

    def _content_hash(self, result: ToolExecutionEnvelope, payload_override: Any = None) -> str:
        payload_json = self.redaction.payload_to_jsonable(payload_override if payload_override is not None else result.result)
        canonical = {
            "tool_name": result.tool_name,
            "information_scope": result.information_scope.value if result.information_scope else None,
            "entity_type": result.entity_type,
            "entity_id": result.entity_id,
            "source_as_of": self._normalize_datetime(self._extract_source_as_of(result)).isoformat()
            if self._normalize_datetime(self._extract_source_as_of(result))
            else None,
            "schema_name": result.schema_name or result.tool_name,
            "schema_version": result.schema_version,
            "payload": payload_json,
            "availability": result.availability,
            "error_codes": list(result.error_codes),
        }
        encoded = json.dumps(canonical, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _extract_source_as_of(self, result: ToolExecutionEnvelope):
        payload = result.result
        if payload is None:
            return None
        if hasattr(payload, "as_of"):
            return getattr(payload, "as_of", None)
        if hasattr(payload, "report_date"):
            return getattr(payload, "report_date", None)
        return None

    def _normalize_datetime(self, value):
        if value is None:
            return None
        if hasattr(value, "tzinfo"):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return None

    def _to_schema(self, row) -> EvidenceArtifact:
        payload = row.payload_json
        return EvidenceArtifact(
            artifact_id=row.id,
            run_id=row.run_id,
            user_id=row.user_id,
            tool_call_id=row.tool_call_id,
            tool_name=row.tool_name,
            information_scope=row.information_scope,
            operation_id=getattr(row, "operation_id", None),
            operation_contract_version=getattr(row, "operation_contract_version", None),
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            asset=row.asset,
            source=row.source,
            resolution_source=row.resolution_source,
            user_scoped=bool(row.user_scoped),
            source_as_of=row.source_as_of,
            freshness=row.freshness,
            schema_name=row.schema_name,
            schema_version=row.schema_version,
            content_hash=row.content_hash,
            payload=parse_tool_payload(row.schema_name, payload),
            availability=row.availability,
            error_codes=list(row.error_codes_json or []),
            created_at=row.created_at or datetime.now(timezone.utc),
            redacted_at=row.redacted_at,
        )
