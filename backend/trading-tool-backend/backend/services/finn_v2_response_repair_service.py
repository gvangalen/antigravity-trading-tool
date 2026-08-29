from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.services.finn_v2_flag_service import FinnV2FlagService


class FinnV2ResponseRepairService:
    REPAIRABLE_CODES = {
        "response_not_answering_question",
        "response_scope_incomplete",
        "response_field_incomplete",
        "missing_uncertainty",
        "mode_purity_violation",
        "unsupported_noncritical_claim",
        "follow_up_invalid",
    }

    def __init__(self, flag_service: Optional[FinnV2FlagService] = None):
        self.flags = flag_service or FinnV2FlagService()

    def can_repair(self, *, reason_codes: list[str], repair_attempt: int) -> bool:
        if not self.flags.is_response_repair_enabled():
            return False
        if repair_attempt >= self.flags.response_max_repair_attempts():
            return False
        return any(code in self.REPAIRABLE_CODES for code in reason_codes)

    def repair(self, *, draft: ResponseDraft, reason_codes: list[str], uncertainty_summary: Optional[str]) -> ResponseDraft:
        updated = draft.copy(deep=True)
        updated.draft_id = f"finn-v2-draft-{uuid.uuid4().hex}"
        updated.created_at = datetime.now(timezone.utc)
        if "follow_up_invalid" in reason_codes:
            updated.follow_up_question = None
        if "missing_uncertainty" in reason_codes and not updated.uncertainty_summary:
            updated.uncertainty_summary = uncertainty_summary or "Een deel van de onderliggende context is onzeker of verouderd."
        if "response_field_incomplete" in reason_codes and updated.mode == "EVALUATE" and not updated.next_step:
            # Coverage requires a concrete, evidence-bounded continuation.
            # Do not fabricate a trade instruction or a causal conclusion.
            updated.next_step = {
                "title": "Onderbouwing aanvullen",
                "instruction": "Controleer de genoemde onderbouwing en vul alleen de ontbrekende of verouderde gegevens aan voordat je het plan wijzigt.",
                "requires_confirmation": False,
            }
        if "unsupported_noncritical_claim" in reason_codes:
            updated.claims = [claim for claim in updated.claims if claim.claim_type in {"uncertainty", "recommendation"} or claim.evidence_refs]
        if "mode_purity_violation" in reason_codes and updated.mode == "READ":
            updated.proposal_candidate = None
            updated.next_step = None
        return ResponseDraft.parse_obj(updated.dict())
