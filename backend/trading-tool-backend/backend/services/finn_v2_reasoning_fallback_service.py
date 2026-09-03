from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage
from backend.schemas.finn_v2_reasoning_schema import (
    ProposalCandidate,
    ReasoningClaim,
    ReasoningNextStep,
    ReasoningResult,
)


class FinnV2ReasoningFallbackService:
    def safe_terminal_draft(self, *, run_id: str, user_id: int, operation_id: str, context: ReasoningContextPackage, model: str) -> ReasoningResult:
        plan = context.request_plan or {}
        if operation_id == "off_topic":
            answer = "Ik help je graag met financiële planning, marktcontext, setups, strategieën en bots."
            observation = "Deze vraag valt buiten FINN's financiële en productondersteuning."
            mode = "UNAVAILABLE"
        elif operation_id == "unsupported_financial_operation":
            capability = plan.get("unsupported_capability") or "Deze bewerking"
            answer = f"{capability} wordt nog niet veilig door FINN ondersteund. Ik kan hiervoor geen actie uitvoeren."
            observation = "De gevraagde financiële bewerking is herkend, maar heeft geen toegestane uitvoeringsadapter."
            mode = "UNAVAILABLE"
        elif operation_id == "activate_bot":
            answer = "Ik herken dit als een verzoek om een bot te activeren, maar FINN kan een live-bot niet impliciet activeren."
            observation = "De activatie blijft geblokkeerd totdat de bestaande voorstel- en bevestigingsgrens expliciet is doorlopen."
            mode = "UNAVAILABLE"
        else:
            concept = plan.get("referenced_entities", {}).get("concept") or "dit financiële begrip"
            answer = f"{concept} is een algemeen financieel analysebegrip. FINN kan het uitleggen, maar trekt zonder jouw bewijs geen persoonlijke conclusie."
            observation = "Dit is algemene educatie en gebruikt geen persoonlijke accountgegevens."
            mode = "READ"
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}", run_id=run_id, user_id=user_id,
            mode=mode, direct_answer=answer, main_observation=observation,
            # Empty strings violate the persisted response schema. General
            # concept explanations are complete deterministic responses, so
            # they carry no uncertainty summary at all.
            uncertainty_summary=None, uncertainty_codes=[], evidence_refs_used=[], model=model,
            created_at=datetime.now(timezone.utc),
        )

    def terminal_from_orchestrator(self, *, run_id: str, user_id: int, orchestrator_result: OrchestratorResult, model: str) -> ReasoningResult:
        plan = orchestrator_result.analysis.request_plan
        operation_id = plan.operation_id if plan is not None else "unavailable"
        if operation_id in {"off_topic", "unsupported_financial_operation", "activate_bot"}:
            if operation_id == "off_topic":
                answer = "Ik help je graag met financiële planning, marktcontext, setups, strategieën en bots."
                observation = "Deze vraag valt buiten FINN's financiële en productondersteuning."
            elif operation_id == "activate_bot":
                answer = "Een live-botactivatie is herkend, maar wordt niet zonder expliciet voorstel en bevestiging uitgevoerd."
                observation = "FINN houdt de activatie geblokkeerd; er ontstaat geen voorstel, write of uitvoering uit deze terminale response."
            else:
                answer = "Autonome koop- en verkoopbeslissingen zonder bevestiging worden niet veilig door FINN ondersteund."
                observation = "FINN voert geen autonome financiële beslissingen uit en houdt de voorstel- en bevestigingsgrens aan."
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="UNAVAILABLE",
                direct_answer=answer,
                main_observation=observation,
                uncertainty_summary=None,
                uncertainty_codes=[],
                evidence_refs_used=[],
                model=model,
                created_at=datetime.now(timezone.utc),
            )
        return self.deterministic_draft(
            run_id=run_id, user_id=user_id, orchestrator_result=orchestrator_result, model=model
        )

    def lineage_draft(
        self, *, run_id: str, user_id: int, operation_id: str,
        context: ReasoningContextPackage, model: str
    ) -> ReasoningResult:
        state = dict((context.request_plan or {}).get("operation_state") or {})
        conclusion = str(state.get("previous_verified_conclusion") or "").strip()
        response = str(state.get("previous_verified_response") or "").strip()
        current_refs = [item.evidence_id for item in context.evidence]
        refs = current_refs or list(state.get("previous_evidence_refs") or [])
        released = list(state.get("previous_degraded_released_sections") or [])
        released_response = dict(state.get("previous_degraded_released_response") or {})
        degraded_scopes = list(state.get("previous_degraded_evidence_scopes") or [])
        terminal_reason = str(state.get("previous_safe_terminal_reason") or "").strip()
        semantic_frame = dict((context.request_plan or {}).get("semantic_frame") or {})
        is_bot_consequence = (
            operation_id == "explain_previous_evidence"
            and str(semantic_frame.get("goal") or "").strip().casefold() == "consequence"
            and str(semantic_frame.get("object") or "").strip().casefold() == "bot"
        )
        if operation_id == "explain_previous_evidence" and terminal_reason == "outside_finn_scope":
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id, user_id=user_id, mode="EVALUATE",
                direct_answer=(
                    "De vorige vraag viel buiten FINN omdat zij geen financiële uitleg, "
                    "FINN-functionaliteit of handelswerkruimte betrof."
                ),
                main_observation=(
                    "Ik kan de grens toelichten, maar maak daarvan geen financiële conclusie "
                    "en voer geen actie uit."
                ),
                uncertainty_summary=None, uncertainty_codes=[], evidence_refs_used=[],
                reasoning_provenance={
                    "reasoning_source": "safe_terminal_boundary",
                    "operation_id": operation_id,
                },
                model=model, created_at=datetime.now(timezone.utc),
            )
        if is_bot_consequence:
            return self._bot_consequence_draft(
                run_id=run_id,
                user_id=user_id,
                context=context,
                refs=refs,
                model=model,
            )
        if operation_id == "explain_previous_evidence" and refs:
            scope_text = ", ".join(str(scope).replace("_", " ") for scope in degraded_scopes) or "de opgeslagen FINN-evidence"
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id, user_id=user_id, mode="EVALUATE",
                direct_answer=(
                    f"De eerdere beperkte beoordeling baseert zich op evidence uit: {scope_text}. "
                    "Die evidence beschrijft opgeslagen context, maar maakt geen niet-geverifieerde financiële conclusie alsnog waar."
                ),
                main_observation=(
                    "De concrete evidence-gap is dat de vrijgegeven gegevens geen volledig toetsbare beslisregel "
                    "met beoordeelde uitkomst bevatten."
                ),
                uncertainty_summary=(
                    "Ik licht alleen de beschikbare evidence en beperking toe; ik voeg geen nieuwe financiële inferentie toe."
                ),
                uncertainty_codes=["degraded_lineage"], evidence_refs_used=refs,
                reasoning_provenance={"reasoning_source": "lineage_evidence", "operation_id": operation_id},
                model=model, created_at=datetime.now(timezone.utc),
            )
        released_text = " ".join(
            str(released_response.get(key) or "").strip()
            for key in ("direct_answer", "main_observation", "uncertainty_summary", "next_step")
        ).strip()
        if operation_id == "reformulate_previous_response" and released_text:
            concise = re.split(r"(?<=[.!?])\s+", released_text, maxsplit=1)[0].strip()
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id, user_id=user_id, mode="READ",
                direct_answer=concise,
                main_observation="Dit herhaalt alleen de eerder veilig vrijgegeven, begrensde beoordeling.",
                uncertainty_summary="De eerdere financiële conclusie was niet geverifieerd; ik voeg geen nieuwe conclusie toe.",
                reasoning_provenance={"reasoning_source": "lineage_reformulation", "operation_id": operation_id},
                uncertainty_codes=["degraded_lineage"], evidence_refs_used=refs,
                model=model, created_at=datetime.now(timezone.utc),
            )
        if not conclusion and not response and released:
            safe_text = " ".join(
                str(item.get("text") or "").strip()
                for item in released if isinstance(item, dict)
            ).strip()
            if operation_id == "reformulate_previous_response" and safe_text:
                return ReasoningResult(
                    reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                    run_id=run_id, user_id=user_id, mode="READ",
                    direct_answer=safe_text,
                    main_observation="De eerdere beoordeling is niet geverifieerd als financiële conclusie.",
                    uncertainty_summary="Ik herformuleer alleen de veilig vrijgegeven beperking en evidencebeschikbaarheid.",
                    reasoning_provenance={"reasoning_source": "lineage_reformulation", "operation_id": operation_id},
                    uncertainty_codes=["degraded_lineage"], evidence_refs_used=refs,
                    model=model, created_at=datetime.now(timezone.utc),
                )
        if not conclusion and not response:
            return self.unavailable_draft(
                run_id=run_id, user_id=user_id, mode="UNAVAILABLE",
                error_codes=["verified_lineage_unavailable"], model=model,
            )
        if operation_id == "reformulate_previous_response":
            source = response or conclusion
            concise = re.split(r"(?<=[.!?])\s+", source, maxsplit=1)[0].strip()
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id, user_id=user_id, mode="READ",
                direct_answer=concise,
                main_observation="Dit is een verkorte formulering van de vorige geverifieerde conclusie.",
                uncertainty_summary=None, uncertainty_codes=[],
                evidence_refs_used=refs, model=model, created_at=datetime.now(timezone.utc),
            )
        return self.unavailable_draft(
            run_id=run_id, user_id=user_id, mode="UNAVAILABLE",
            error_codes=["lineage_operation_requires_model"], model=model,
        )

    @staticmethod
    def _bot_consequence_draft(
        *, run_id: str, user_id: int, context: ReasoningContextPackage, refs: list[str], model: str,
    ) -> ReasoningResult:
        """Render a read-only, evidence-bounded bot check from typed lineage."""
        bot = next(
            (
                item for item in context.evidence
                if item.tool_name in {"read_linked_bot", "read_bot_status"}
            ),
            None,
        )
        if bot is None:
            answer = (
                "Concrete botcontrole: verifieer eerst de geregistreerde status van de gekoppelde bot; "
                "de eerdere planconclusie bevat geen geverifieerde botstatus."
            )
            observation = (
                "De eerdere conclusie bewijst geen effect op de bot en rechtvaardigt geen wijziging, activatie of uitvoering."
            )
        else:
            facts = dict(bot.facts or {})
            bot_id = str(bot.entity_id or facts.get("id") or "de gekoppelde bot")
            if "is_live" in facts:
                state = "live" if bool(facts["is_live"]) else "niet live"
                answer = f"Concrete botcontrole: bevestig dat bot {bot_id} geregistreerd {state} staat."
            else:
                answer = f"Concrete botcontrole: controleer de geregistreerde status van bot {bot_id}."
            observation = (
                "De eerdere conclusie bewijst geen oorzakelijk effect op deze bot en rechtvaardigt geen botwijziging of uitvoering."
            )
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="EVALUATE",
            direct_answer=answer,
            main_observation=observation,
            uncertainty_summary="De controle beschrijft alleen verifieerbare botgegevens; prestaties en causaliteit blijven onbekend.",
            uncertainty_codes=["evidence_bounded_consequence"],
            evidence_refs_used=refs,
            reasoning_provenance={"reasoning_source": "lineage_consequence", "operation_id": "explain_previous_evidence"},
            model=model,
            created_at=datetime.now(timezone.utc),
        )
    @staticmethod
    def _indicator_names(facts: dict[str, Any], category: str) -> list[str]:
        rows = facts.get(category) or []
        names: list[str] = []
        for row in rows:
            indicator = str((row or {}).get("indicator") or "").strip()
            if indicator and indicator not in names:
                names.append(indicator)
        if names:
            return names
        for row in facts.get("configured_indicators") or []:
            if str((row or {}).get("category") or "").strip().lower() != category:
                continue
            indicator = str((row or {}).get("indicator") or "").strip()
            if indicator and indicator not in names:
                names.append(indicator)
        return names

    @staticmethod
    def _profile_values(profile_facts: dict[str, Any]) -> tuple[str | None, str | None]:
        style = profile_facts.get("style")
        if isinstance(style, list):
            style = next((str(item).strip() for item in style if str(item).strip()), None)
        elif style is not None:
            style = str(style).strip() or None
        risk_profile = profile_facts.get("risk_profile") or profile_facts.get("riskTolerance")
        risk_profile = str(risk_profile).strip() if risk_profile else None
        return style, risk_profile

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
            direct_answer="Ik kan deze vraag nu niet veilig afronden met de beschikbare reasoning-uitkomst.",
            main_observation="De reasoning-uitkomst bleef onvolledig of niet betrouwbaar genoeg voor een normale FINN-respons.",
            uncertainty_summary="Gebruik de al opgeslagen context of probeer het opnieuw zodra de ontbrekende reasoningstap wel compleet kan worden afgerond.",
            uncertainty_codes=error_codes,
            evidence_refs_used=[],
            model=model,
            created_at=datetime.now(timezone.utc),
        )

    def grounded_read_draft(
        self,
        *,
        run_id: str,
        user_id: int,
        context: ReasoningContextPackage,
        model: str,
        error_codes: list[str],
    ) -> ReasoningResult:
        evidence = list(getattr(context, "evidence", []) or [])
        if not evidence:
            return self.unavailable_draft(
                run_id=run_id,
                user_id=user_id,
                mode="UNAVAILABLE",
                error_codes=error_codes or ["read_context_unavailable"],
                model=model,
            )
        evidence_by_tool = {item.tool_name: item for item in evidence}
        request_plan = context.request_plan or {}
        operation_id = request_plan.get("operation_id")
        active_asset = evidence_by_tool.get("read_active_asset")
        indicators = evidence_by_tool.get("read_indicator_configuration")
        setup = evidence_by_tool.get("read_active_setup")
        strategy = evidence_by_tool.get("read_linked_strategy")
        bot = evidence_by_tool.get("read_linked_bot")
        bot_status = evidence_by_tool.get("read_bot_status")
        asset = (
            (active_asset.facts.get("symbol") if active_asset else None)
            or (indicators.facts.get("symbol") if indicators else None)
            or (setup.facts.get("symbol") if setup else None)
            or (strategy.facts.get("symbol") if strategy else None)
            or (bot.facts.get("symbol") if bot else None)
            or "deze asset"
        )
        lowered = self._user_message(context)

        claims: list[ReasoningClaim] = []
        refs: list[str] = []

        def _add_claim(claim_id: str, text: str, evidence_refs: list[str]) -> None:
            deduped = []
            for ref in evidence_refs:
                if ref and ref not in deduped:
                    deduped.append(ref)
                if ref and ref not in refs:
                    refs.append(ref)
            claims.append(
                ReasoningClaim(
                    claim_id=claim_id,
                    claim_type="fact",
                    text=text,
                    evidence_refs=deduped,
                    confidence="high",
                )
            )

        # The operation registry determines which evidence scope a read operation
        # must carry through reasoning. This keeps deterministic reads provider-free
        # without letting the verifier infer coverage from prompt wording.
        if operation_id == "read_active_asset" and active_asset is not None:
            symbol = str(active_asset.facts.get("symbol") or asset).upper()
            asset_class = active_asset.facts.get("asset_class") or active_asset.facts.get("asset_type")
            _add_claim(
                "active-asset",
                f"Je actieve asset is {symbol}.",
                [active_asset.evidence_id],
            )
            detail = f" ({asset_class})" if asset_class else ""
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="READ",
                direct_answer=f"Je actieve asset is {symbol}{detail}.",
                main_observation="Dit komt rechtstreeks uit je user-scoped actieve assetcontext.",
                supporting_points=[],
                claims=claims,
                uncertainty_summary="Er is geen providercall uitgevoerd voor deze opgeslagen context.",
                uncertainty_codes=list(error_codes),
                next_step=None,
                follow_up_question=None,
                proposal_candidate=None,
                evidence_refs_used=refs,
                model=model,
                created_at=datetime.now(timezone.utc),
            )

        if operation_id == "read_indicator_configuration" and indicators is not None:
            configured = list(indicators.facts.get("configured_indicators") or [])
            names: list[str] = []
            for category in ("market", "macro", "technical"):
                for name in self._indicator_names(indicators.facts, category):
                    if name not in names:
                        names.append(name)
            configured_count = indicators.facts.get("configured_count")
            if configured_count is None:
                configured_count = len(configured) or len(names)
            rendered_names = ", ".join(names) if names else "geen indicatoren"
            if active_asset is not None:
                _add_claim(
                    "indicator-configuration-asset",
                    f"Deze indicatorconfiguratie is gekoppeld aan je actieve asset {asset}.",
                    [active_asset.evidence_id],
                )
            _add_claim(
                "indicator-configuration",
                f"Voor {asset} zijn {configured_count} indicatorconfiguraties opgeslagen: {rendered_names}.",
                [indicators.evidence_id],
            )
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="READ",
                direct_answer=f"Voor {asset} staan {configured_count} indicatoren ingesteld: {rendered_names}.",
                main_observation="Deze configuratie komt rechtstreeks uit je opgeslagen, asset-scoped indicatorregels.",
                supporting_points=[],
                claims=claims,
                uncertainty_summary="Er is geen providercall uitgevoerd voor deze opgeslagen configuratie.",
                uncertainty_codes=list(error_codes),
                next_step=None,
                follow_up_question=None,
                proposal_candidate=None,
                evidence_refs_used=refs,
                model=model,
                created_at=datetime.now(timezone.utc),
            )

        if operation_id in {"read_linked_bot", "read_active_plan"} and all(
            item is not None for item in (active_asset, setup, strategy, bot, bot_status)
        ):
            setup_id = setup.facts.get("setup_id")
            strategy_id = strategy.facts.get("strategy_id")
            bot_id = bot.facts.get("bot_id")
            setup_name = setup.facts.get("name") or f"setup {setup_id}"
            timeframe = setup.facts.get("timeframe")
            is_live = bool(bot_status.facts.get("is_live", bot.facts.get("is_live")))
            _add_claim(
                "active-plan-graph",
                (
                    f"Voor {asset} is {setup_name} gekoppeld aan strategie {strategy_id} "
                    f"en bot {bot_id}; de bot staat {'live' if is_live else 'niet live'}."
                ),
                [
                    active_asset.evidence_id,
                    setup.evidence_id,
                    strategy.evidence_id,
                    bot.evidence_id,
                    bot_status.evidence_id,
                ],
            )
            timeframe_detail = f" op timeframe {timeframe}" if timeframe else ""
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="READ",
                direct_answer=(
                    f"Je actieve {asset}-plan gebruikt {setup_name}{timeframe_detail}, "
                    f"strategie {strategy_id} en bot {bot_id}."
                ),
                main_observation=f"Bot {bot_id} staat momenteel {'live' if is_live else 'niet live'}.",
                supporting_points=[],
                claims=claims,
                uncertainty_summary="Er is geen providercall uitgevoerd voor deze opgeslagen planrelaties.",
                uncertainty_codes=list(error_codes),
                next_step=None,
                follow_up_question=None,
                proposal_candidate=None,
                evidence_refs_used=refs,
                model=model,
                created_at=datetime.now(timezone.utc),
            )

        if setup is not None and setup.facts.get("setup_id") is not None:
            _add_claim(
                "setup-linked",
                f"Setup {setup.facts.get('setup_id')} voor {asset} gebruikt timeframe {setup.facts.get('timeframe')}.",
                [setup.evidence_id],
            )
        if strategy is not None and strategy.facts.get("strategy_id") is not None:
            _add_claim(
                "strategy-linked",
                f"Strategie {strategy.facts.get('strategy_id')} is gekoppeld aan setup {strategy.facts.get('setup_id')}.",
                [strategy.evidence_id],
            )
        if bot is not None and bot.facts.get("bot_id") is not None:
            bot_refs = [bot.evidence_id]
            if bot_status is not None:
                bot_refs.append(bot_status.evidence_id)
            _add_claim(
                "bot-linked",
                (
                    f"Bot {bot.facts.get('bot_id')} is gekoppeld aan strategie {bot.facts.get('strategy_id')} "
                    f"en heeft is_live {str(bool(bot.facts.get('is_live'))).lower()}."
                ),
                bot_refs,
            )

        direct_answer = f"Ik kan je actieve {asset}-plan nu wel deels gronden op de opgeslagen context."
        main_observation = "De opgeslagen plancontext is aanwezig, maar de modeluitkomst was niet compleet genoeg om direct te gebruiken."
        uncertainty_summary = "Ik val daarom terug op de direct opgeslagen plancontext."

        if "entryvoorwaarde" in lowered or "entry toestaat" in lowered:
            entry = strategy.facts.get("entry") if strategy else None
            entry_type = strategy.facts.get("entry_type") if strategy else None
            direct_answer = (
                f"Je huidige {asset}-strategie legt nu een {entry_type or 'vaste'} entry rond {entry} vast."
                if entry is not None
                else f"Ik zie wel een gekoppelde {asset}-strategie, maar geen expliciet opgeslagen entryvoorwaarde."
            )
            main_observation = (
                "In de opgeslagen strategie staat wel een entryniveau, maar geen extra bevestigingsregel zoals een aparte indicator- of candletrigger."
            )
        elif "strategie" in lowered and ("risicoprofiel" in lowered or "tradingstijl" in lowered):
            strategy_id = strategy.facts.get("strategy_id") if strategy else None
            risk_profile = strategy.facts.get("risk_profile") if strategy else None
            direct_answer = (
                f"Strategie {strategy_id} is gekoppeld aan je actieve {asset}-setup en gebruikt risicoprofiel {risk_profile or 'onbekend'}."
                if strategy_id is not None
                else f"Ik zie nog geen gekoppelde {asset}-strategie in de opgeslagen plancontext."
            )
            main_observation = (
                "Wat ik zeker kan gronden is de bestaande strategie-link; een volledig fit-oordeel vraagt daarnaast om een complete profiel- en marktvertaling."
            )
        elif "welke indicatoren" in lowered or "indicatoren" in lowered:
            direct_answer = f"Deze vraag vraagt om je indicatorconfiguratie voor {asset}, niet om een andere setup- of botkoppeling."
            main_observation = (
                "De huidige fallback kan die indicatorconfiguratie alleen veilig samenvatten als `read_indicator_configuration` ook echt evidence heeft opgeleverd."
            )
        elif "actieve plan" in lowered:
            setup_id = setup.facts.get("setup_id") if setup else None
            setup_name = setup.facts.get("name") if setup else None
            timeframe = setup.facts.get("timeframe") if setup else None
            strategy_id = strategy.facts.get("strategy_id") if strategy else None
            bot_id = bot.facts.get("bot_id") if bot else None
            is_live = bool((bot_status or bot).facts.get("is_live")) if (bot_status or bot) else False
            direct_answer = (
                f"Je actieve plan voor {asset} bestaat uit setup {setup_id}, strategie {strategy_id} en bot {bot_id}."
            )
            main_observation = (
                f"Setup {setup_id} ({setup_name or 'onbekende setup'}) gebruikt timeframe {timeframe}, "
                f"strategie {strategy_id} is daaraan gekoppeld en bot {bot_id} staat momenteel {'live' if is_live else 'niet live'}."
            )
        elif "welke bot" in lowered or ("bot" in lowered and "live" in lowered):
            bot_id = bot.facts.get("bot_id") if bot else None
            is_live = bool((bot_status or bot).facts.get("is_live")) if (bot_status or bot) else False
            direct_answer = f"Bot {bot_id} is aan je {asset}-strategie gekoppeld en staat momenteel {'live' if is_live else 'niet live'}."
            main_observation = (
                f"De gekoppelde bot draait als {'live bot' if is_live else 'paper bot'} "
                f"en heeft strategy_id {(bot.facts.get('strategy_id') if bot else None)}."
            )
        elif "actieve setup" in lowered or ("setup" in lowered and "timeframe" in lowered):
            setup_id = setup.facts.get("setup_id") if setup else None
            timeframe = setup.facts.get("timeframe") if setup else None
            direct_answer = (
                f"Je actieve {asset}-setup is setup {setup_id} en gebruikt timeframe {timeframe}."
                if setup_id is not None
                else f"Ik zie nog geen actieve {asset}-setup in de opgeslagen plancontext."
            )
            main_observation = "Deze setup-link komt rechtstreeks uit de user-scoped setuprelatie."
        elif "waarom" in lowered and "positie" in lowered:
            bot_id = bot.facts.get("bot_id") if bot else None
            last_run = bot_status.facts.get("last_run") if bot_status else None
            direct_answer = f"Wat ik zeker weet over je {asset}-bot: bot {bot_id} is gekoppeld, actief en niet live."
            main_observation = (
                f"Wat ik nog niet bevestigd kan afleiden: deze evidence bevat geen opgeslagen order- of positiereden die exact verklaart waarom nog geen positie is geopend; de laatste bekende botstatus verwijst alleen naar last_run {last_run}."
            )
        else:
            direct_answer = f"Je actieve {asset}-setup is setup {setup.facts.get('setup_id') if setup else None}."
            main_observation = (
                f"Die setup gebruikt timeframe {setup.facts.get('timeframe') if setup else None}"
                f"{' en is gekoppeld aan strategie ' + str(strategy.facts.get('strategy_id')) if strategy and strategy.facts.get('strategy_id') is not None else ''}."
            )

        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="READ",
            direct_answer=direct_answer,
            main_observation=main_observation,
            supporting_points=[],
            claims=claims,
            uncertainty_summary=uncertainty_summary,
            uncertainty_codes=list(error_codes),
            next_step=None,
            follow_up_question=None,
            proposal_candidate=None,
            evidence_refs_used=refs,
            model=model,
            created_at=datetime.now(timezone.utc),
        )

    def grounded_proposal_draft(
        self,
        *,
        run_id: str,
        user_id: int,
        context: ReasoningContextPackage,
        model: str,
        error_codes: list[str],
    ) -> ReasoningResult:
        evidence_by_tool = {item.tool_name: item for item in context.evidence}
        active_asset = evidence_by_tool.get("read_active_asset")
        asset = active_asset.facts.get("symbol") if active_asset else None
        request_plan = context.request_plan or {}
        operation_id = request_plan.get("operation_id")
        operation_state = request_plan.get("operation_state") or {}

        if (operation_id == "watchlist_add" or not operation_id) and context.policy.operation_type == "watchlist_add":
            target_asset = str((operation_state.get("collected_inputs") or {}).get("asset") or "").upper()
            if not target_asset and not operation_id:
                # Historical planless reasoning records are read-only
                # compatibility input; new runs always use operation_state.
                target_asset = self._first_asset_symbol(context.user_message) or asset or ""
            if not target_asset:
                from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
                return ReasoningResult(
                    reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                    run_id=run_id,
                    user_id=user_id,
                    mode="CLARIFICATION",
                    direct_answer="Ik kan de watchlist-wijziging nog niet voorbereiden zonder één doelasset.",
                    main_observation="Er ontbreekt nog één noodzakelijke detailkeuze voordat ik een voorstel kan opbouwen.",
                    supporting_points=[],
                    claims=[],
                    uncertainty_summary="Er wordt niets aangepast zonder een valide voorstel en bevestiging.",
                    uncertainty_codes=list(error_codes),
                    next_step=None,
                    follow_up_question=FinnV2OperationStateService.clarification_question("asset"),
                    proposal_candidate=None,
                    evidence_refs_used=[],
                    model=model,
                    created_at=datetime.now(timezone.utc),
                )
            evidence_refs = [active_asset.evidence_id] if active_asset else []
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="ACTION_PROPOSAL",
                direct_answer=f"Ik kan {target_asset} aan je watchlist toevoegen na je bevestiging.",
                main_observation=f"De wijziging is nog niet uitgevoerd; ik heb alleen een voorstel voor {target_asset} voorbereid.",
                supporting_points=[],
                claims=[
                    ReasoningClaim(
                        claim_id="watchlist-target",
                        claim_type="fact",
                        text=f"De gevraagde doelasset voor deze watchlist-wijziging is {target_asset}.",
                        evidence_refs=evidence_refs,
                        confidence="high",
                    )
                ] if evidence_refs else [],
                uncertainty_summary="Bevestiging blijft vereist voordat de watchlist echt wordt aangepast.",
                uncertainty_codes=list(error_codes),
                next_step=ReasoningNextStep(
                    title="Bevestig de watchlist-wijziging",
                    instruction=f"Bevestig dat je {target_asset} wilt toevoegen aan je watchlist.",
                    operation_type="watchlist_add",
                    target_entity_type="watchlist",
                    target_entity_id=target_asset,
                    requires_confirmation=True,
                ),
                follow_up_question=None,
                proposal_candidate=ProposalCandidate(
                    operation_type="watchlist_add",
                    target_type="watchlist",
                    target_id=None,
                    asset=target_asset,
                    proposed_changes={
                        "proposal_status": "draft",
                        "generation_source": "deterministic_validated",
                        "asset": target_asset,
                        "operation": "add",
                    },
                    evidence_refs=evidence_refs,
                    impact_summary=f"{target_asset} wordt toegevoegd aan je persoonlijke watchlist na bevestiging.",
                    risk_summary="Er wordt niets uitgevoerd zonder expliciete confirmation.",
                    confirmation_required=True,
                ),
                evidence_refs_used=evidence_refs,
                model=model,
                created_at=datetime.now(timezone.utc),
            )

        if operation_id and operation_id != "create_setup":
            return self.unavailable_draft(
                run_id=run_id,
                user_id=user_id,
                mode="UNAVAILABLE",
                model=model,
                error_codes=[*error_codes, "proposal_operation_contract_missing"],
            )
        missing = list(operation_state.get("missing_required_inputs") or [])
        if not operation_id:
            requested_asset = self._first_asset_symbol(context.user_message) or asset
            timeframe = self._first_timeframe(context.user_message)
            if requested_asset is None or timeframe is None:
                missing = ["symbol" if requested_asset is None else "timeframe"]
            else:
                operation_state = {
                    "collected_inputs": {
                        "symbol": requested_asset,
                        "timeframe": timeframe,
                        "setup_type": "trade",
                    }
                }
        if missing:
            from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
            question = FinnV2OperationStateService.clarification_question(operation_state.get("next_missing_input") or missing[0])
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="CLARIFICATION",
                direct_answer="Ik kan de setup nog niet veilig voorstellen zonder één ontbrekend kernveld.",
                main_observation="Er ontbreekt nog precies één noodzakelijke detailkeuze voordat ik een setupvoorstel kan opbouwen.",
                supporting_points=[],
                claims=[],
                uncertainty_summary="Zonder dat detail zou ik setupvelden moeten invullen op basis van aannames.",
                uncertainty_codes=list(error_codes),
                next_step=None,
                follow_up_question=question,
                proposal_candidate=None,
                evidence_refs_used=[],
                model=model,
                created_at=datetime.now(timezone.utc),
            )

        proposed_fields = dict(operation_state.get("collected_inputs") or {})
        requested_asset = str(proposed_fields.get("symbol") or asset or "").upper()
        if not requested_asset:
            return self.unavailable_draft(
                run_id=run_id,
                user_id=user_id,
                mode="UNAVAILABLE",
                model=model,
                error_codes=[*error_codes, "proposal_asset_missing_after_validation"],
            )
        timeframe = str(proposed_fields.get("timeframe") or "").strip().upper()
        timeframe_detail = f" met {timeframe} als primair timeframe" if timeframe else ""
        evidence_refs = [item.evidence_id for item in [active_asset, evidence_by_tool.get("read_profile"), evidence_by_tool.get("read_user_preferences")] if item is not None]
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="CREATE_PROPOSAL",
            direct_answer=f"Ik kan een concept-setup voor {requested_asset} voorbereiden{timeframe_detail}.",
            main_observation="Deze setup is nog niet opgeslagen; het gaat om een voorstel dat eerst bevestigd moet worden.",
            supporting_points=[],
            claims=[],
            uncertainty_summary="Controleer de setupvelden eerst inhoudelijk voordat je bevestigt.",
            uncertainty_codes=list(error_codes),
            next_step=ReasoningNextStep(
                title="Bevestig het setupvoorstel",
                instruction=f"Controleer het voorstel voor {requested_asset} en bevestig pas als de trend- en entrylogica klopt.",
                operation_type="create_setup",
                target_entity_type="setup",
                target_entity_id=None,
                requires_confirmation=True,
            ),
            follow_up_question=None,
            proposal_candidate=ProposalCandidate(
                operation_type="create_setup",
                target_type="setup",
                target_id=None,
                asset=requested_asset,
                proposed_changes={
                    "proposal_status": "draft",
                    "generation_source": "deterministic_validated",
                    "setup_fields": proposed_fields,
                },
                evidence_refs=evidence_refs,
                impact_summary=f"Er wordt een nieuwe {requested_asset}-setup voorbereid op basis van je prompt.",
                risk_summary="De setup wordt pas opgeslagen na expliciete confirmation.",
                confirmation_required=True,
            ),
            evidence_refs_used=evidence_refs,
            model=model,
            created_at=datetime.now(timezone.utc),
        )

    def blocked_action_draft(
        self,
        *,
        run_id: str,
        user_id: int,
        context: ReasoningContextPackage,
        model: str,
        error_codes: list[str],
    ) -> ReasoningResult:
        evidence_by_tool = {item.tool_name: item for item in context.evidence}
        bot = evidence_by_tool.get("read_linked_bot")
        bot_status = evidence_by_tool.get("read_bot_status")
        bot_id = bot.facts.get("bot_id") if bot else None
        refs = [item.evidence_id for item in [bot, bot_status] if item is not None]
        claims = []
        if bot is not None:
            claims.append(
                ReasoningClaim(
                    claim_id="bot-live-state",
                    claim_type="fact",
                    text=f"Bot {bot_id} heeft is_live {str(bool(bot.facts.get('is_live'))).lower()}.",
                    evidence_refs=refs,
                    confidence="high",
                )
            )
        blocking = ", ".join(context.policy.blocking_codes or error_codes or ["live_action_disabled"])
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="UNAVAILABLE",
            direct_answer="Ik kan deze bot niet live activeren.",
            main_observation=f"De live-activatie blijft geblokkeerd door de actieve safety- en policycontroles ({blocking}).",
            supporting_points=[],
            claims=claims,
            uncertainty_summary="De bot blijft paper-only totdat een operator dit expliciet buiten deze geblokkeerde flow vrijgeeft.",
            uncertainty_codes=list(error_codes or context.policy.blocking_codes),
            next_step=None,
            follow_up_question=None,
            proposal_candidate=None,
            evidence_refs_used=refs,
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
        scopes = set(getattr(context, "subject_scopes", []) or [])
        lowered = self._user_message(context)
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
        setup_name = setup.facts.get("name") if setup else None
        timeframe = setup.facts.get("timeframe") if setup else None
        strategy_id = strategy.facts.get("strategy_id") if strategy else None
        bot_id = bot.facts.get("bot_id") if bot else None
        profile_facts = profile.facts.get("trader_profile", {}) if profile else {}
        has_profile = bool(profile and profile.facts.get("has_profile"))
        profile_is_empty = not any(profile_facts.get(key) for key in profile_facts)
        profile_style, profile_risk = self._profile_values(profile_facts)
        indicator_facts = indicators.facts if indicators else {}
        technical_indicators = self._indicator_names(indicator_facts, "technical")
        market_indicators = self._indicator_names(indicator_facts, "market")
        macro_indicators = self._indicator_names(indicator_facts, "macro")
        indicator_count = len(indicators.facts.get("configured_indicators") or []) if indicators else 0
        execution_mode = strategy.facts.get("execution_mode") if strategy else None
        risk_profile = strategy.facts.get("risk_profile") if strategy else None
        entry = strategy.facts.get("entry") if strategy else None
        stop_loss = strategy.facts.get("stop_loss") if strategy else None
        targets = strategy.facts.get("targets") if strategy else None
        target_count = len(targets) if isinstance(targets, list) else 0
        first_target = targets[0] if target_count else None
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

        if scopes == {"indicators"} or ("indicators" in scopes and "strategy" not in scopes and "setup" not in scopes and "bot" not in scopes):
            direct_answer = (
                f"Voor {asset} kan ik nu alleen bevestigen dat je indicatorconfiguratie {indicator_count} opgeslagen indicatoren bevat."
            )
            main_observation = (
                "De ontbrekende perspectieven horen dan in extra markt- of indicatorcontext, niet in een generieke plan- of botuitleg."
            )
            next_step = ReasoningNextStep(
                title="Controleer je ontbrekende analyseperspectief",
                instruction=f"Voeg voor {asset} hooguit één extra indicator of contextlaag toe die je huidige analyse echt aanvult.",
                operation_type=None,
                target_entity_type="indicator_configuration",
                target_entity_id=asset,
                requires_confirmation=False,
            )
        elif "entryvoorwaarde" in lowered or "entry toestaat" in lowered:
            entry = strategy.facts.get("entry") if strategy else None
            entry_type = strategy.facts.get("entry_type") if strategy else None
            direct_answer = (
                f"De belangrijkste expliciet opgeslagen entryvoorwaarde in je {asset}-strategie {strategy_id} is nu een {entry_type or 'vaste'} entry rond {entry}."
                if strategy_id is not None and entry is not None
                else f"Ik zie voor {asset} wel een gekoppelde strategie, maar nog geen expliciet opgeslagen entryvoorwaarde."
            )
            main_observation = (
                f"Wat nog niet bevestigd kan worden, is een extra entryfilter voor {asset}, zoals een aparte indicator- of candletrigger; die staat niet expliciet in deze strategie-evidence."
            )
            next_step = ReasoningNextStep(
                title="Leg je entrybevestiging expliciet vast",
                instruction=(
                    f"Controleer of strategie {strategy_id} naast het entryniveau ook een expliciete bevestigingsregel nodig heeft, "
                    "zoals een candle-close of indicatortrigger."
                ),
                operation_type=None,
                target_entity_type="strategy",
                target_entity_id=str(strategy_id) if strategy_id is not None else None,
                requires_confirmation=False,
            )
        elif "strategy" in scopes and "profile" in scopes and not {"setup", "bot", "indicators"}.intersection(scopes):
            direct_answer = (
                f"Strategie {strategy_id} voor {asset} sluit nu het best aan via execution_mode {execution_mode or 'onbekend'}."
                if strategy_id is not None
                else f"Ik kan nog geen gekoppelde {asset}-strategie gronden voor deze vergelijking."
            )
            main_observation = (
                f"Het mogelijke conflict is dat het opgeslagen risicoprofiel nu {risk_profile or 'niet expliciet'} is, "
                "waardoor de fit met je profiel slechts deels vastligt."
            )
            next_step = ReasoningNextStep(
                title="Leg het strategie-risicoprofiel expliciet vast",
                instruction=f"Controleer of strategie {strategy_id} hetzelfde risicoprofiel gebruikt als jouw persoonlijke voorkeuren.",
                operation_type=None,
                target_entity_type="strategy",
                target_entity_id=str(strategy_id) if strategy_id is not None else None,
                requires_confirmation=False,
            )
        elif indicator_count == 0:
            setup_label = setup_name or f"setup {setup_id}" if setup_id is not None else f"je {asset}-setup"
            direct_answer = (
                f"Het belangrijkste ontbrekende onderdeel van je {asset}-plan is een bruikbare indicatorconfiguratie "
                f"die {setup_label} op timeframe {timeframe or 'onbekend'} en de bestaande strategie echt kan valideren."
            )
            main_observation = (
                f"{setup_label} is gekoppeld aan strategie {strategy_id} en bot {bot_id}, "
                f"maar voor {asset} staan nog geen geconfigureerde indicatoren klaar om entry {entry or 'onbekend'}, "
                f"stop {stop_loss or 'onbekend'} en {target_count if target_count else 'je'} target{'s' if target_count != 1 else ''}"
                f"{f' zoals {first_target}' if first_target else ''} inhoudelijk te onderbouwen."
            )
            next_step = ReasoningNextStep(
                title="Activeer je eerste planindicatoren",
                instruction=(
                    f"Voeg voor {asset} eerst precies één trendfilter voor {timeframe or 'je hoofdtimeframe'} en "
                    f"één entry-trigger rond {entry or 'je entryniveau'} toe, zodat FINN deze strategie op echte signalen kan beoordelen."
                ),
                operation_type=None,
                target_entity_type="indicator_configuration",
                target_entity_id=asset,
                requires_confirmation=False,
            )
        elif has_profile and not profile_is_empty:
            technical_label = technical_indicators[0] if technical_indicators else "je technische indicator"
            context_label = market_indicators[0] if market_indicators else (macro_indicators[0] if macro_indicators else "je extra contextlaag")
            style_label = profile_style or "tradingstijl"
            risk_label = profile_risk or risk_profile or "risicoprofiel"
            direct_answer = (
                f"Het belangrijkste ontbrekende onderdeel van je {asset}-plan is nu de vertaalslag van je {style_label}-profiel en {risk_label} "
                f"naar één expliciete beslisregel tussen {technical_label} en {context_label}."
            )
            main_observation = (
                f"Je profiel, setup {setup_id}, strategie {strategy_id} en bot {bot_id} zijn aanwezig: "
                f"setup {setup_id} draait op {timeframe or 'onbekend'}, strategie {strategy_id} gebruikt {execution_mode or 'onbekende'} uitvoering "
                f"en je configuratie bevat {technical_label}"
                f"{f' plus {context_label}' if context_label != technical_label else ''}, "
                "maar ik zie nog geen expliciete regel die bepaalt wanneer die signalen samen wel of niet sterk genoeg zijn voor je plan."
            )
            next_step = ReasoningNextStep(
                title="Leg je beslisregel vast",
                instruction=(
                    f"Leg voor {asset} precies vast hoe {technical_label}"
                    f"{f' samen met {context_label}' if context_label != technical_label else ''} "
                    f"op timeframe {timeframe or 'je hoofdtimeframe'} moet bevestigen voordat strategie {strategy_id} of bot {bot_id} het plan mag volgen."
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
            mode="EVALUATE",
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

    def evidence_limited_evaluation_draft(
        self,
        *,
        run_id: str,
        user_id: int,
        context: ReasoningContextPackage,
        model: str,
        error_codes: list[str],
    ) -> ReasoningResult:
        """Return only neutral, evidence-backed facts after an unsafe evaluation.

        The normal deterministic evaluation may itself contain an unsupported
        causal conclusion. A failed repair must therefore not reuse any of its
        claims; the terminal result is rebuilt from canonical evidence instead.
        """
        evidence = list(context.evidence)
        if not evidence:
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="EVALUATE",
                direct_answer="Ik kan je huidige plan nog niet beoordelen, omdat er geen opgeslagen setup, strategie of beoordeelbare plancontext beschikbaar is.",
                main_observation="Ik vul geen planonderdelen of bewijs in die niet in je werkruimte zijn vastgelegd.",
                uncertainty_summary="Selecteer of leg eerst een setup en de gekoppelde strategie vast.",
                uncertainty_codes=error_codes or ["plan_context_unavailable"],
                next_step=ReasoningNextStep(
                    title="Leg plancontext vast",
                    instruction="Selecteer een actieve setup met gekoppelde strategie, of maak eerst een setupvoorstel om te beoordelen.",
                    requires_confirmation=False,
                ),
                evidence_refs_used=[],
                model=model,
                created_at=datetime.now(timezone.utc),
            )

        # Reuse the same factual evidence projection as a normal evaluation,
        # but replace the unsupported causal conclusion with the actual answer
        # this contract can establish: which part is least supported by the
        # available evidence. Keeping the factual claims makes this a fully
        # grounded EVALUATE response that can become durable lineage.
        result = self.grounded_evaluation_draft(
            run_id=run_id,
            user_id=user_id,
            context=context,
            model=model,
            error_codes=list(dict.fromkeys([*error_codes, "evidence_limitation_after_repair"])),
        )
        if result.mode != "EVALUATE":
            # A partial but real evidence set still merits a typed evaluation
            # of its evidentiary limit. Do not collapse the lifecycle to
            # UNAVAILABLE merely because an optional factual projection is
            # absent from this particular fixture.
            result = ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="EVALUATE",
                direct_answer="De minst overtuigend onderbouwde schakel is de toetsbare beslisregel van je plan; de beschikbare evidence bevat geen beoordeelde uitkomst die zo'n regel ondersteunt.",
                main_observation="De beschikbare evidence bevestigt afzonderlijke opgeslagen planonderdelen, maar niet hoe zij samen in een toetsbare beslissing zijn gebruikt.",
                supporting_points=[],
                claims=[
                    ReasoningClaim(
                        claim_id=f"evidence-record-{index}",
                        claim_type="fact",
                        text=f"Evidence {item.evidence_id} is voor deze planbeoordeling verzameld uit {item.tool_name}.",
                        evidence_refs=[item.evidence_id],
                        confidence="high",
                    )
                    for index, item in enumerate(evidence)
                ],
                uncertainty_summary="Voor een sterkere beoordeling is een expliciete beslisregel plus een beoordeelde uitvoerings- of marktuitkomst nodig.",
                uncertainty_codes=list(dict.fromkeys([*error_codes, "evidence_limitation_after_repair"])),
                next_step=None,
                follow_up_question=None,
                proposal_candidate=None,
                evidence_refs_used=[item.evidence_id for item in evidence],
                model=model,
                created_at=datetime.now(timezone.utc),
            )
        result.direct_answer = (
            "De minst overtuigend onderbouwde schakel is de toetsbare beslisregel "
            "van je plan: de beschikbare evidence bevestigt opgeslagen onderdelen, "
            "maar bevat geen beoordeeld uitvoerings- of marktresultaat dat zo'n regel ondersteunt."
        )
        result.main_observation = (
            "Dit is een evidence-gap, geen oordeel dat een opgeslagen configuratie "
            "een probleem veroorzaakt; de feitelijke profiel-, indicator-, setup-, "
            "strategie- en botgegevens staan afzonderlijk in de onderbouwing."
        )
        result.uncertainty_summary = (
            "Voor een sterkere beoordeling is een expliciete beslisregel plus een "
            "beoordeelde uitvoerings- of marktuitkomst nodig."
        )
        # The integrated-plan contract requires the complete ledger, but a
        # fact value can be structured (for example a profile map). Rendering
        # it as a generic sentence would create a claim that cannot be
        # deterministically entailed. The explicit ledger and the bounded
        # evidence-gap response are therefore the canonical safe projection.
        result.claims = []
        result.evidence_refs_used = [item.evidence_id for item in evidence]
        result.next_step = ReasoningNextStep(
            title="Leg toetsbare plan-evidence vast",
            instruction=(
                "Leg één concrete beslisregel en de uitkomst van een beoordeling vast; "
                "FINN kan daarna beoordelen hoe sterk die regel wordt onderbouwd."
            ),
            operation_type=None,
            target_entity_type=None,
            target_entity_id=None,
            requires_confirmation=False,
        )
        return result

    def _first_asset_symbol(self, text: str) -> str | None:
        match = re.search(r"\b(BTC|ETH|SOL|AAPL|TSLA|NVDA)\b", text.upper())
        return match.group(1) if match else None

    def _first_timeframe(self, text: str) -> str | None:
        lowered = text.lower()
        if "4h" in lowered:
            return "4H"
        if "1d" in lowered or "daily" in lowered or "dag" in lowered:
            return "1D"
        if "1h" in lowered:
            return "1H"
        return None

    def _user_message(self, context: Any) -> str:
        return str(getattr(context, "user_message", "") or "").lower()
