from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_shadow_comparison_repository import FinnV2ShadowComparisonRepository
from backend.schemas.finn_v2_cutover_schema import FinnV2ShadowComparisonResult


class FinnV2ShadowComparisonService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = FinnV2ShadowComparisonRepository(session)

    async def compare(
        self,
        *,
        surface: str,
        v1_response: dict[str, Any],
        v2_response: dict[str, Any],
        run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        latency_delta_ms: Optional[int] = None,
        cost_delta_estimate: Optional[float] = None,
    ) -> FinnV2ShadowComparisonResult:
        v1_text = json.dumps(v1_response, sort_keys=True, default=str).lower()
        v2_text = json.dumps(v2_response, sort_keys=True, default=str).lower()
        mode_match = str(v1_response.get("intent") or "").upper() == str(v2_response.get("mode") or v2_response.get("intent") or "").upper()
        asset_match = self._extract_asset(v1_text) == self._extract_asset(v2_text)
        follow_up_count_match = int(bool(v1_response.get("next_question"))) == int(bool(v2_response.get("follow_up_question")))
        safety_match = "executed" not in v2_text and "uitgevoerd" not in v2_text
        reason_codes: list[str] = []
        if not asset_match:
            reason_codes.append("asset_mismatch")
        if not safety_match:
            reason_codes.append("unsafe_execution_language")
        if not mode_match:
            reason_codes.append("mode_mismatch")
        if not follow_up_count_match:
            reason_codes.append("follow_up_mismatch")
        outcome = "equivalent"
        if not safety_match:
            outcome = "v2_unsafe"
        elif len(v2_text) > len(v1_text) and asset_match:
            outcome = "v2_better"
        elif v1_text == v2_text:
            outcome = "equivalent"
        else:
            outcome = "v1_better" if len(v1_text) > len(v2_text) else "ungradable"
        record = FinnV2ShadowComparisonResult(
            comparison_id=f"finn-v2-shadow-comparison-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            surface=surface,
            outcome=outcome,
            mode_match=mode_match,
            asset_match=asset_match,
            follow_up_count_match=follow_up_count_match,
            safety_match=safety_match,
            latency_delta_ms=latency_delta_ms,
            cost_delta_estimate=cost_delta_estimate,
            reason_codes=reason_codes,
            created_at=datetime.now(timezone.utc),
        )
        await self.repo.create(
            id=record.comparison_id,
            run_id=record.run_id,
            user_id=record.user_id,
            surface=record.surface,
            outcome=record.outcome,
            result_json=record.dict(),
            reason_codes_json=record.reason_codes,
            created_at=record.created_at,
        )
        return record

    def _extract_asset(self, payload: str) -> Optional[str]:
        for token in ["btc", "eth", "sol", "aapl", "nvda", "tsla"]:
            if token in payload:
                return token.upper()
        return None


def redacted_hash_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

