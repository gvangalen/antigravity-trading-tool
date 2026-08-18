from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from backend.schemas.finn_v2_reasoning_schema import ReasoningNextStep, ReasoningResult, ReasoningSupportingPoint


CAPABILITY_REGISTRY_VERSION = "2026-08-18.block6.capability"


@dataclass(frozen=True)
class CapabilityEntry:
    capability_id: str
    title: str
    description: str
    action_class: str
    financial_risk: str
    user_financial_context_required: bool
    claimable: bool = True


class FinnV2CapabilityRegistryService:
    _CAPABILITY_MATCHERS = (
        "wat kun je voor mij doen",
        "waarmee kun je mij helpen",
        "wat doet finn",
        "hoe kun je mijn plan beoordelen",
        "hoe kun je me helpen",
        "hoe kan finn helpen",
        "what can you do for me",
        "what can finn do",
        "how can you help me",
        "how can you review my plan",
        "what do you do",
    )

    _ENTRIES: tuple[CapabilityEntry, ...] = (
        CapabilityEntry(
            capability_id="profile_preferences_explain",
            title="Profiel en voorkeuren duiden",
            description="FINN kan je profiel, voorkeuren en huidige context samenvatten en uitleggen wat nog ontbreekt.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="asset_indicator_context_explain",
            title="Assets en indicatorcontext uitleggen",
            description="FINN kan je actieve asset, indicatorconfiguratie en bijbehorende context uitleggen zodra die beschikbaar is.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="market_macro_technical_explain",
            title="Markt-, macro- en technische context uitleggen",
            description="FINN kan markt-, macro- en technische data in gewone taal toelichten zonder daar meteen een trade van te maken.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="setup_strategy_bot_review",
            title="Setup, strategie en bot beoordelen",
            description="FINN kan setups, strategieen en gekoppelde bots uitleggen en veilig reviewen zodra die context bestaat.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="reports_reviews_explain",
            title="Reports en reviews toelichten",
            description="FINN kan rapporten, reflecties en eerdere reviews samenvatten en toelichten.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="missing_context_signal",
            title="Ontbrekende context signaleren",
            description="FINN geeft aan welke context nog ontbreekt voordat een specifiek financieel oordeel veilig is.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="proposal_prepare",
            title="Wijzigingen als voorstel voorbereiden",
            description="FINN kan veilige wijzigingen als voorstel voorbereiden, maar voert niets stilzwijgend uit.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="safe_confirmed_execution",
            title="Veilige wijzigingen pas na bevestiging uitvoeren",
            description="FINN voert pas een toegestane wijziging uit na de juiste bevestigingsflow en safety checks.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
        CapabilityEntry(
            capability_id="no_unsecured_live_orders",
            title="Geen live orders zonder beveiligde flow",
            description="FINN plaatst geen live orders buiten een afzonderlijke beveiligde en toegestane flow.",
            action_class="READ_ONLY",
            financial_risk="NONE",
            user_financial_context_required=False,
        ),
    )

    def is_capability_question(self, message: str) -> bool:
        normalized = str(message or "").strip().casefold()
        return any(phrase in normalized for phrase in self._CAPABILITY_MATCHERS)

    def registry_version(self) -> str:
        return CAPABILITY_REGISTRY_VERSION

    def claimable_entries(self) -> List[CapabilityEntry]:
        return [entry for entry in self._ENTRIES if entry.claimable]

    def claimable_titles(self) -> set[str]:
        return {entry.title for entry in self.claimable_entries()}

    def capability_ids(self) -> set[str]:
        return {entry.capability_id for entry in self.claimable_entries()}

    def describe_for_prompt(self) -> list[dict]:
        return [
            {
                "capability_id": entry.capability_id,
                "title": entry.title,
                "description": entry.description,
                "action_class": entry.action_class,
                "financial_risk": entry.financial_risk,
                "user_financial_context_required": entry.user_financial_context_required,
            }
            for entry in self.claimable_entries()
        ]

    def build_reasoning_result(
        self,
        *,
        run_id: str,
        user_id: int,
        user_message: str,
        locale: str,
        model: str,
        missing_context: Optional[Iterable[str]] = None,
        asset: Optional[str] = None,
        profile_completed: bool = False,
    ) -> ReasoningResult:
        asset_suffix = f" rond {str(asset).upper()}" if asset else ""
        missing = [str(item) for item in (missing_context or []) if item]
        direct_answer = (
            "Ik kan je helpen om je tradingcontext te begrijpen, ontbrekende informatie zichtbaar te maken "
            "en veilige vervolgstappen voor te bereiden."
        )
        observation = (
            "Hoe meer profiel-, asset- en plancontext je invult, hoe persoonlijker FINN kan uitleggen, beoordelen en coachen."
        )
        if profile_completed and asset:
            observation = (
                f"Met jouw huidige context{asset_suffix} kan FINN gerichter uitleg geven over setups, strategieen, bots en reviews."
            )

        points = [
            ReasoningSupportingPoint(
                title="Profiel en voorkeuren duiden",
                explanation="Ik kan je profiel, voorkeuren en huidige context uitleggen en laten zien wat nog ontbreekt.",
                evidence_refs=[],
            ),
            ReasoningSupportingPoint(
                title="Assets en indicatorcontext uitleggen",
                explanation="Ik kan assets, indicatorconfiguratie en marktcontext in gewone taal toelichten zodra die beschikbaar zijn.",
                evidence_refs=[],
            ),
            ReasoningSupportingPoint(
                title="Setup, strategie en bot beoordelen",
                explanation="Ik kan setups, strategieen en gekoppelde bots veilig reviewen zonder direct iets uit te voeren.",
                evidence_refs=[],
            ),
            ReasoningSupportingPoint(
                title="Wijzigingen als voorstel voorbereiden",
                explanation="Ik kan veilige wijzigingen als voorstel voorbereiden en pas na bevestiging naar een toegestane vervolgflow sturen.",
                evidence_refs=[],
            ),
        ]

        next_step = None
        if missing:
            first = missing[0]
            labels = {
                "profile": "vul je profiel aan",
                "asset": "kies een asset",
                "setup": "voeg een setup toe",
                "strategy": "koppel een strategie",
                "bot": "koppel een bot",
                "scores": "laad je analysecontext",
                "latest_report": "genereer of open een rapport",
            }
            step_label = labels.get(first, "vul je context verder aan")
            next_step = ReasoningNextStep(
                title="Maak je context persoonlijker",
                instruction=f"Begin met: {step_label}. Daarna kan FINN je veel gerichter helpen.",
                operation_type=None,
                target_entity_type=None,
                target_entity_id=None,
                requires_confirmation=False,
            )
        elif not profile_completed:
            next_step = ReasoningNextStep(
                title="Versterk je profiel",
                instruction="Rond eerst je profiel en voorkeuren af, zodat FINN je antwoorden gerichter kan personaliseren.",
                operation_type=None,
                target_entity_type=None,
                target_entity_id=None,
                requires_confirmation=False,
            )

        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-capability-{user_id}-{int(datetime.now(timezone.utc).timestamp())}",
            run_id=run_id,
            user_id=user_id,
            mode="CAPABILITY",
            direct_answer=direct_answer,
            main_observation=observation,
            supporting_points=points,
            claims=[],
            uncertainty_summary=None,
            uncertainty_codes=[],
            next_step=next_step,
            follow_up_question=None,
            proposal_candidate=None,
            evidence_refs_used=[],
            prompt_version=CAPABILITY_REGISTRY_VERSION,
            reasoning_version=CAPABILITY_REGISTRY_VERSION,
            model=model,
            created_at=datetime.now(timezone.utc),
        )
