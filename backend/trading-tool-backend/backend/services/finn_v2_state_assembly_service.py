from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_tools import FINN_V2_TOOL_ORDER
from backend.infrastructure.repositories.finn_v2_evidence_repository import FinnV2EvidenceRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.schemas.finn_v2_evidence_schema import EvidenceArtifact, PAYLOAD_TYPE_TO_SCHEMA_NAME, parse_tool_payload
from backend.schemas.finn_v2_state_schema import (
    ASSEMBLY_VERSION,
    EvidenceReference,
    FinancialStateSnapshot,
    StateEdge,
    StateNode,
    ToolOutcome,
)
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_state_redaction_service import FinnV2StateRedactionService


class FinnV2StateAssemblyService:
    def __init__(self, session: AsyncSession, flag_service: FinnV2FlagService | None = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.artifacts = FinnV2EvidenceRepository(session)
        self.snapshots = FinnV2StateRepository(session)
        self.redaction = FinnV2StateRedactionService()

    async def assemble_for_run(self, *, run_id: str, user_id: int) -> FinancialStateSnapshot:
        artifacts = [self._coerce_artifact(row) for row in await self.artifacts.list_for_run(run_id=run_id, user_id=user_id)]
        evidence_set_hash = self._evidence_set_hash(artifacts)
        existing = await self.snapshots.get_by_evidence_hash(run_id=run_id, user_id=user_id, evidence_set_hash=evidence_set_hash)
        if existing is not None:
            return FinancialStateSnapshot(**(existing.snapshot_json or {}))

        nodes = self._build_nodes(artifacts)
        edges = self._build_edges(nodes)
        tool_outcomes = self._build_tool_outcomes(artifacts)
        revision = await self.snapshots.next_revision(run_id=run_id, user_id=user_id)
        snapshot = FinancialStateSnapshot(
            snapshot_id=f"finn-v2-snapshot-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            revision=revision,
            evidence_set_hash=evidence_set_hash,
            nodes=nodes,
            edges=edges,
            tool_outcomes=tool_outcomes,
            assembled_at=datetime.now(timezone.utc),
        )
        payload = self.redaction.enforce_max_bytes(
            snapshot.dict(),
            max_bytes=self.flags.state_max_payload_bytes(),
            label="financial_state_snapshot",
        )
        await self.snapshots.create(
            id=snapshot.snapshot_id,
            run_id=run_id,
            user_id=user_id,
            revision=revision,
            schema_version=snapshot.schema_version,
            assembly_version=ASSEMBLY_VERSION,
            evidence_set_hash=evidence_set_hash,
            snapshot_json=payload,
            assembled_at=snapshot.assembled_at,
        )
        return snapshot

    def _coerce_artifact(self, row) -> EvidenceArtifact:
        return EvidenceArtifact(
            artifact_id=row.id,
            run_id=row.run_id,
            user_id=row.user_id,
            tool_call_id=row.tool_call_id,
            tool_name=row.tool_name,
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
            payload=parse_tool_payload(row.schema_name, row.payload_json),
            availability=row.availability,
            error_codes=list(row.error_codes_json or []),
            created_at=row.created_at,
            redacted_at=row.redacted_at,
        )

    def _build_nodes(self, artifacts: list[EvidenceArtifact]) -> list[StateNode]:
        node_map: dict[str, StateNode] = {}
        for artifact in artifacts:
            node = self._node_for_artifact(artifact)
            if node is not None:
                node_map[node.node_id] = node
        return list(node_map.values())

    def _node_for_artifact(self, artifact: EvidenceArtifact) -> StateNode | None:
        mapping = {
            "read_profile": ("profile", "profile", "profile"),
            "read_user_preferences": ("preferences", "preferences", "preferences"),
            "read_active_asset": (f"asset:{artifact.asset or artifact.entity_id or 'unknown'}", "asset", "active_asset"),
            "read_indicator_configuration": ("indicator_configuration", "indicator_configuration", "indicator_configuration"),
            "read_asset_scores": ("scores", "scores", "asset_scores"),
            "read_market_snapshot": ("market_snapshot", "market_snapshot", "market_snapshot"),
            "read_macro_snapshot": ("macro_snapshot", "macro_snapshot", "macro_snapshot"),
            "read_technical_snapshot": ("technical_snapshot", "technical_snapshot", "technical_snapshot"),
            "read_active_setup": (f"setup:{artifact.entity_id or 'unknown'}", "setup", "active_setup"),
            "read_linked_strategy": (f"strategy:{artifact.entity_id or 'unknown'}", "strategy", "linked_strategy"),
            "read_linked_bot": (f"bot:{artifact.entity_id or 'unknown'}", "bot", "linked_bot"),
            "read_bot_status": ("bot_status", "bot_status", "bot_status"),
            "read_watchlist": ("watchlist", "watchlist", "watchlist"),
            "read_portfolio": ("portfolio", "portfolio", "portfolio"),
            "read_latest_report": ("latest_report", "latest_report", "latest_report"),
            "read_review_history": ("review_history", "review_history", "review_history"),
        }
        if artifact.tool_name not in mapping:
            return None
        node_id, entity_type, payload_type = mapping[artifact.tool_name]
        parsed_payload = parse_tool_payload(PAYLOAD_TYPE_TO_SCHEMA_NAME.get(payload_type), artifact.payload)
        return StateNode(
            node_id=node_id,
            entity_type=entity_type,
            entity_id=artifact.entity_id,
            asset=artifact.asset,
            payload_type=payload_type,
            payload=parsed_payload,
            availability=artifact.availability,
            freshness=artifact.freshness,
            confidence=self._node_confidence(artifact.availability, artifact.freshness),
            evidence=[self._artifact_ref(artifact)],
            issue_codes=list(artifact.error_codes),
        )

    def _build_edges(self, nodes: list[StateNode]) -> list[StateEdge]:
        node_map = {node.node_id: node for node in nodes}
        pairs = [
            ("profile", "preferences", "has_preferences"),
            ("profile", next((key for key in node_map if key.startswith("asset:")), None), "focuses_on_asset"),
            (next((key for key in node_map if key.startswith("asset:")), None), "indicator_configuration", "has_indicator_configuration"),
            (next((key for key in node_map if key.startswith("asset:")), None), "scores", "has_scores"),
            (next((key for key in node_map if key.startswith("asset:")), None), "market_snapshot", "has_market_snapshot"),
            (next((key for key in node_map if key.startswith("asset:")), None), "macro_snapshot", "has_macro_snapshot"),
            (next((key for key in node_map if key.startswith("asset:")), None), "technical_snapshot", "has_technical_snapshot"),
            (next((key for key in node_map if key.startswith("asset:")), None), next((key for key in node_map if key.startswith("setup:")), None), "has_setup"),
            (next((key for key in node_map if key.startswith("setup:")), None), next((key for key in node_map if key.startswith("strategy:")), None), "has_strategy"),
            (next((key for key in node_map if key.startswith("strategy:")), None), next((key for key in node_map if key.startswith("bot:")), None), "has_bot"),
            (next((key for key in node_map if key.startswith("bot:")), None), "bot_status", "has_bot_status"),
            ("profile", "watchlist", "has_watchlist"),
            ("profile", "portfolio", "has_portfolio"),
            ("profile", "latest_report", "has_latest_report"),
            ("profile", "review_history", "has_review_history"),
        ]
        edges: list[StateEdge] = []
        for from_id, to_id, relation in pairs:
            if not from_id or not to_id:
                continue
            if from_id not in node_map or to_id not in node_map:
                continue
            edges.append(
                StateEdge(
                    from_node_id=from_id,
                    to_node_id=to_id,
                    relation=relation,
                    confidence="high" if node_map[from_id].availability == "available" and node_map[to_id].availability == "available" else "medium",
                    evidence=node_map[to_id].evidence,
                )
            )
        return edges

    def _build_tool_outcomes(self, artifacts: list[EvidenceArtifact]) -> list[ToolOutcome]:
        by_name = {artifact.tool_name: artifact for artifact in artifacts}
        outcomes: list[ToolOutcome] = []
        for tool_name in FINN_V2_TOOL_ORDER:
            artifact = by_name.get(tool_name)
            if artifact is None:
                outcomes.append(ToolOutcome(tool_name=tool_name, status="not_collected", artifact_id=None, error_codes=["evidence_not_collected"]))
                continue
            status = "failed" if artifact.error_codes and artifact.availability == "unavailable" else artifact.availability
            outcomes.append(ToolOutcome(tool_name=tool_name, status=status, artifact_id=artifact.artifact_id, error_codes=list(artifact.error_codes)))
        return outcomes

    def _artifact_ref(self, artifact: EvidenceArtifact) -> EvidenceReference:
        return EvidenceReference(
            artifact_id=artifact.artifact_id,
            tool_call_id=artifact.tool_call_id,
            tool_name=artifact.tool_name,
            content_hash=artifact.content_hash,
            source=artifact.source,
            source_as_of=artifact.source_as_of,
        )

    def _node_confidence(self, availability: str, freshness: str) -> str:
        if availability == "not_collected":
            return "none"
        if availability in {"ambiguous", "unavailable"}:
            return "low"
        if freshness == "stale":
            return "medium"
        return "high"

    def _evidence_set_hash(self, artifacts: list[EvidenceArtifact]) -> str:
        canonical = [
            {
                "artifact_id": artifact.artifact_id,
                "tool_name": artifact.tool_name,
                "content_hash": artifact.content_hash,
                "availability": artifact.availability,
            }
            for artifact in sorted(artifacts, key=lambda row: (row.tool_call_id, row.artifact_id))
        ]
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
