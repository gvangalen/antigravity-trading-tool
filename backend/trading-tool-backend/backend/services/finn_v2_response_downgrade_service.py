from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_response_schema import ResponseDraft


class FinnV2ResponseDowngradeService:
    @staticmethod
    def _language(draft: ResponseDraft) -> str:
        return str((draft.reasoning_provenance or {}).get("locale") or "nl").split("-", 1)[0].casefold()

    def downgrade_to_fact(self, *, draft: ResponseDraft) -> ResponseDraft:
        """Retain the legacy verifier action name while emitting a canonical READ draft."""
        claims = [claim for claim in draft.claims if claim.claim_type in {"fact", "uncertainty"} and claim.evidence_refs]
        supporting_points = [point for point in draft.supporting_points if point.evidence_refs][:4]
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="READ",
            direct_answer=draft.direct_answer,
            main_observation=draft.main_observation,
            supporting_points=supporting_points,
            claims=claims,
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=draft.uncertainty_summary,
            uncertainty_codes=list(draft.uncertainty_codes),
            next_step=None,
            follow_up_question=None,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )

    def downgrade_to_clarification(self, *, draft: ResponseDraft, orchestrator_result: OrchestratorResult) -> ResponseDraft:
        question = draft.follow_up_question or (
            orchestrator_result.selected_clarification.question if orchestrator_result.selected_clarification else "Welke keuze wil je dat ik beoordeel?"
        )
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="CLARIFICATION",
            direct_answer="Ik mis nog een noodzakelijke keuze om dit veilig en precies te beantwoorden.",
            main_observation="De huidige context laat meerdere geldige interpretaties toe.",
            supporting_points=[],
            claims=[],
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=None,
            uncertainty_codes=[],
            next_step=None,
            follow_up_question=question,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )

    def downgrade_to_unavailable(self, *, draft: ResponseDraft, reason: Optional[str]) -> ResponseDraft:
        language = self._language(draft)
        copy = {
            "en": (
                "I cannot provide a safely grounded answer yet.",
                "The available context does not fully support this response.",
                "Try again with the relevant saved setup, strategy, or asset selected.",
            ),
            "de": (
                "Ich kann darauf noch keine sicher belegte Antwort geben.",
                "Der verfuegbare Kontext stuetzt diese Antwort noch nicht vollstaendig.",
                "Versuche es erneut mit dem passenden gespeicherten Setup, der Strategie oder dem ausgewaehlten Asset.",
            ),
        }.get(language, (
            "Ik kan hier nog geen veilig onderbouwd antwoord op geven.",
            "De beschikbare context ondersteunt deze reactie nog niet volledig.",
            "Probeer opnieuw met de relevante opgeslagen setup, strategie of asset geselecteerd.",
        ))
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="UNAVAILABLE",
            direct_answer=copy[0],
            # Internal verifier codes remain in the trace, never user copy.
            main_observation=copy[1],
            supporting_points=[],
            claims=[],
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=copy[2],
            uncertainty_codes=[],
            next_step=None,
            follow_up_question=None,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )

    def downgrade_to_contract_limited_evaluate(self, *, draft: ResponseDraft, reason: Optional[str]) -> ResponseDraft:
        """Keep an evidence-backed evaluation visible after bounded repair.

        This is not a financial conclusion. It explains the available evidence
        boundary and gives one concrete safe next step, rather than erasing a
        valid EVALUATE intent into a generic unavailable response.
        """
        provenance = dict(draft.reasoning_provenance or {})
        language = self._language(draft)
        asset = str(provenance.get("target_asset") or "").upper()
        subject = f" for {asset}" if asset and language == "en" else (f" fuer {asset}" if asset and language == "de" else (f" voor {asset}" if asset else ""))
        copy = {
            "en": (
                f"I can summarize the verified context{subject}, but the available evidence is not complete enough for a full assessment.",
                "I will not add a trading conclusion that the stored evidence does not support.",
                "Add or select the missing plan or market context, then I can reassess the same question.",
            ),
            "de": (
                f"Ich kann den bestaetigten Kontext{subject} zusammenfassen, aber die vorhandenen Nachweise reichen noch nicht fuer eine vollstaendige Bewertung.",
                "Ich fuege keine Handelsfolgerung hinzu, die durch die gespeicherten Nachweise nicht belegt ist.",
                "Ergaenze oder waehle den fehlenden Plan- oder Marktkontext aus; danach kann ich dieselbe Frage erneut bewerten.",
            ),
        }.get(language, (
            f"Ik kan de geverifieerde context{subject} samenvatten, maar de beschikbare evidence is nog niet compleet genoeg voor een volledige beoordeling.",
            "Ik voeg geen handelsconclusie toe die niet door de opgeslagen evidence wordt ondersteund.",
            "Vul of selecteer de ontbrekende plan- of marktcontext; daarna kan ik dezelfde vraag opnieuw beoordelen.",
        ))
        provenance.update(
            {
                "reasoning_source": "contract_evidence_limitation",
                "validation_status": "evidence_limited",
                "terminal_limitation_reason": reason or "response_verification_limited",
            }
        )
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="EVALUATE",
            direct_answer=copy[0],
            main_observation=copy[1],
            supporting_points=[],
            claims=[],
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=copy[2],
            uncertainty_codes=list(dict.fromkeys([*draft.uncertainty_codes, "evidence_limitation_after_repair"])),
            next_step={
                "title": {"en": "Complete the assessment context", "de": "Bewertungskontext ergaenzen"}.get(language, "Vul beoordelingscontext aan"),
                "instruction": copy[2],
                "requires_confirmation": False,
            },
            follow_up_question=None,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            reasoning_provenance=provenance,
            created_at=datetime.now(timezone.utc),
        )
