from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage
from backend.schemas.finn_v2_reasoning_schema import (
    ReasoningClaim,
    ReasoningNextStep,
    ReasoningResult,
)


class FinnV2ReasoningFallbackService:
    def deterministic_draft(self, *, run_id: str, user_id: int, orchestrator_result: OrchestratorResult, model: str) -> ReasoningResult:
        mode = orchestrator_result.outcome
        if mode == "clarification_required":
            question = orchestrator_result.selected_clarification.question if orchestrator_result.selected_clarification else "Welke verduidelijking heb je precies nodig?"
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="CLARIFICATION",
                direct_answer="Ik kan nog geen verantwoorde trade of financiële conclusie geven met de huidige context.",
                main_observation="Er ontbreekt nog één noodzakelijke verduidelijking voordat ik dit veilig kan beoordelen.",
                uncertainty_summary="Zonder die extra context zou ik moeten gokken.",
                uncertainty_codes=orchestrator_result.unavailable_codes,
                follow_up_question=question,
                evidence_refs_used=[],
                model=model,
                created_at=datetime.now(timezone.utc),
            )
        asset = orchestrator_result.analysis.explicit_asset
        next_question = (
            f"Wil je eerst je huidige setup voor {asset} laten beoordelen?"
            if asset
            else "Wil je eerst aangeven over welke asset of setup je dit wilt bekijken?"
        )
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="UNAVAILABLE",
            direct_answer="Ik kan nog geen verantwoorde trade aanwijzen, omdat essentiële markt- of setupcontext ontbreekt.",
            main_observation="Zonder actuele context, een geldige setup en voldoende onderbouwing zou ik een financiële conclusie verzinnen.",
            uncertainty_summary=next_question,
            uncertainty_codes=orchestrator_result.unavailable_codes or orchestrator_result.uncertainty_codes,
            follow_up_question=next_question,
            evidence_refs_used=[],
            model=model,
            created_at=datetime.now(timezone.utc),
        )

    def unavailable_draft(self, *, run_id: str, user_id: int, mode: str, error_codes: list[str], model: str) -> ReasoningResult:
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode=mode,
            direct_answer="FINN V2 reasoning is momenteel niet beschikbaar voor deze shadowrun.",
            main_observation="De centrale AI-runtime of configuratie liet geen veilige reasoningcall toe.",
            uncertainty_summary="De analyse is deterministisch afgebroken voordat een modelcall werd gedaan.",
            uncertainty_codes=error_codes,
            evidence_refs_used=[],
            model=model,
            created_at=datetime.now(timezone.utc),
        )

    def grounded_evaluation_draft(
        self,
        *,
        run_id: str,
        user_id: int,
        context: ReasoningContextPackage,
        model: str,
        error_codes: list[str],
    ) -> ReasoningResult:
        evidence_by_tool = {item.tool_name: item for item in context.evidence}
        profile = evidence_by_tool.get("read_profile")
        indicators = evidence_by_tool.get("read_indicator_configuration")
        setup = evidence_by_tool.get("read_active_setup")
        strategy = evidence_by_tool.get("read_linked_strategy")
        bot = evidence_by_tool.get("read_linked_bot")
        bot_status = evidence_by_tool.get("read_bot_status")
        asset = (
            (setup.facts.get("symbol") if setup else None)
            or (strategy.facts.get("symbol") if strategy else None)
            or (indicators.facts.get("symbol") if indicators else None)
            or "deze asset"
        )
        setup_id = setup.facts.get("setup_id") if setup else None
        strategy_id = strategy.facts.get("strategy_id") if strategy else None
        bot_id = bot.facts.get("bot_id") if bot else None
        profile_facts = profile.facts.get("trader_profile", {}) if profile else {}
        has_profile = bool(profile and profile.facts.get("has_profile"))
        profile_is_empty = not any(profile_facts.get(key) for key in profile_facts)
        indicator_count = len(indicators.facts.get("configured_indicators") or []) if indicators else 0
        execution_mode = strategy.facts.get("execution_mode") if strategy else None
        is_live = bool(bot.facts.get("is_live")) if bot else False
        is_active = bool(bot_status.facts.get("is_active")) if bot_status else bool(bot and bot.facts.get("is_active"))

        direct_answer = f"Het belangrijkste ontbrekende onderdeel van je {asset}-plan is een expliciet risicokader dat je profiel, strategie en botinstelling aan elkaar koppelt."
        main_observation = (
            f"Setup {setup_id} en strategie {strategy_id} bestaan al en bot {bot_id} staat als paper bot klaar, "
            f"maar je profiel is nog leeg en strategie {strategy_id} heeft nog geen expliciet risicoprofiel."
        )
        next_step = ReasoningNextStep(
            title="Leg je risicokader vast",
            instruction=(
                f"Leg voor strategie {strategy_id} eerst één concreet risicoprofiel en maximaal risico per trade vast, "
                "zodat FINN je BTC-plan inhoudelijk tegen je eigen grenzen kan toetsen."
            ),
            operation_type=None,
            target_entity_type="strategy",
            target_entity_id=str(strategy_id) if strategy_id is not None else None,
            requires_confirmation=False,
        )

        if indicator_count == 0:
            direct_answer = f"Het belangrijkste ontbrekende onderdeel van je {asset}-plan is een bruikbare indicatorconfiguratie die je setup en strategie echt ondersteunt."
            main_observation = (
                f"Setup {setup_id}, strategie {strategy_id} en bot {bot_id} zijn gekoppeld, "
                f"maar voor {asset} staan nog geen geconfigureerde indicatoren klaar om je entries en trendfilter te onderbouwen."
            )
            next_step = ReasoningNextStep(
                title="Activeer je eerste planindicatoren",
                instruction=(
                    f"Voeg voor {asset} eerst je belangrijkste trend- en entry-indicatoren toe, "
                    "zodat FINN je bestaande setup en strategie op echte signalen kan beoordelen."
                ),
                operation_type=None,
                target_entity_type="indicator_configuration",
                target_entity_id=asset,
                requires_confirmation=False,
            )
        elif has_profile and not profile_is_empty:
            direct_answer = f"Het belangrijkste ontbrekende onderdeel van je {asset}-plan is een expliciete koppeling tussen je huidige marktcontext en de voorwaarden van strategie {strategy_id}."
            main_observation = (
                f"Je profiel, setup {setup_id}, strategie {strategy_id} en bot {bot_id} zijn aanwezig, "
                "maar de huidige beoordeling mist nog een expliciete vertaalslag van context naar concrete planvoorwaarden."
            )
            next_step = ReasoningNextStep(
                title="Toets je setup aan je context",
                instruction=(
                    f"Controleer eerst of setup {setup_id} en strategie {strategy_id} nog passen bij de huidige marktstructuur, "
                    "voordat je de bot verder laat volgen."
                ),
                operation_type=None,
                target_entity_type="setup",
                target_entity_id=str(setup_id) if setup_id is not None else None,
                requires_confirmation=False,
            )

        uncertainty = "Deze beoordeling is deterministisch opgebouwd omdat de modelreasoning tijdelijk niet bruikbaar was."
        if context.uncertainty_codes:
            uncertainty = (
                "Deze beoordeling is gebaseerd op je opgeslagen plancontext; een deel van de markt- of brondata was beperkt beschikbaar."
            )

        claims = []
        if profile is not None:
            claims.append(
                ReasoningClaim(
                    claim_id="profile-status",
                    claim_type="fact",
                    text=f"Je profielrecord voor deze run heeft has_profile {str(profile.facts.get('has_profile')).lower()}.",
                    evidence_refs=[profile.evidence_id],
                    confidence="high",
                )
            )
        if indicators is not None:
            claims.append(
                ReasoningClaim(
                    claim_id="indicator-status",
                    claim_type="fact",
                    text=f"Voor {asset} bevat je indicatorconfiguratie {indicator_count} configured_indicators.",
                    evidence_refs=[indicators.evidence_id],
                    confidence="high",
                )
            )
        if setup is not None and setup_id is not None:
            claims.append(
                ReasoningClaim(
                    claim_id="setup-status",
                    claim_type="fact",
                    text=f"Setup {setup_id} voor {asset} gebruikt timeframe {setup.facts.get('timeframe')}.",
                    evidence_refs=[setup.evidence_id],
                    confidence="high",
                )
            )
        if strategy is not None and strategy_id is not None:
            claims.append(
                ReasoningClaim(
                    claim_id="strategy-status",
                    claim_type="fact",
                    text=f"Strategie {strategy_id} voor setup {setup_id} gebruikt execution_mode {execution_mode}.",
                    evidence_refs=[strategy.evidence_id],
                    confidence="high",
                )
            )
        if bot is not None and bot_status is not None and bot_id is not None:
            claims.append(
                ReasoningClaim(
                    claim_id="bot-status",
                    claim_type="fact",
                    text=(
                        f"Bot {bot_id} is gekoppeld aan strategie {strategy_id}, "
                        f"heeft is_live {str(is_live).lower()} en is_active {str(is_active).lower()}."
                    ),
                    evidence_refs=[bot.evidence_id, bot_status.evidence_id],
                    confidence="high",
                )
            )

        evidence_refs_used = []
        for claim in claims:
            for ref in claim.evidence_refs:
                if ref not in evidence_refs_used:
                    evidence_refs_used.append(ref)

        if not claims:
            return self.unavailable_draft(
                run_id=run_id,
                user_id=user_id,
                mode="UNAVAILABLE",
                error_codes=error_codes or ["deterministic_evaluation_insufficient_evidence"],
                model=model,
            )

        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="EVALUATION",
            direct_answer=direct_answer,
            main_observation=main_observation,
            supporting_points=[],
            claims=claims,
            uncertainty_summary=uncertainty,
            uncertainty_codes=list(error_codes),
            next_step=next_step,
            follow_up_question=None,
            proposal_candidate=None,
            evidence_refs_used=evidence_refs_used,
            model=model,
            created_at=datetime.now(timezone.utc),
        )
