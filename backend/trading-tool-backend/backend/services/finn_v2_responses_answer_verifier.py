"""Verify a model-composed read answer against owner-scoped tool evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import asyncio
import json
import logging
import os
import re
from typing import Any
from langdetect import DetectorFactory, LangDetectException, detect, detect_langs

from backend.services.asset_catalog_service import mentioned_catalog_symbols
from backend.services.finn_v2_responses_loop import (
    FinnResponsesError,
    FinnResponsesResult,
    _read_only_stop_loss_coaching,
    _hypothetical_trade_reflection,
    _rule_objection,
    _saved_confirmation_readback,
    limited_evaluation_answer,
    limited_evaluation_format,
    plan_review_next_step_from_evidence,
)
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds
from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService
from backend.services.finn_v2_verified_turn_context import project_verified_turn
from backend.services.finn_v2_hard_claim_boundary import FinnV2HardClaimBoundary
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinnResponsesVerifiedAnswer:
    status: str
    text: str
    reason: str | None
    evidence: tuple[dict[str, Any], ...]
    used_previous_response: bool = False
    clarification: dict[str, str] | None = None
    rejection_details: dict[str, Any] | None = None


class FinnResponsesAnswerVerifier:
    def __init__(self, semantic: FinnV2SemanticVerifierService | None = None, client: Any = None) -> None:
        self.semantic = semantic or FinnV2SemanticVerifierService()
        self.client = client

    @staticmethod
    def _emotional_coach_fallback(message: str, locale: str | None) -> str | None:
        """Offer a safe process question when an emotional coaching draft fails verification."""
        language = locale if locale in {"nl", "en", "de"} else "nl"
        if re.search(r"\b(?:fomo|fear of missing out|bang[^.!?]{0,35}missen|afraid[^.!?]{0,35}miss|bewegung[^.!?]{0,35}verpass)\b", message, re.I):
            if re.search(r"\b(?:wachtregel|wachten op bevestiging|wait rule|wait for confirmation|Warteregel|Bestätigung warten)\b", message, re.I):
                return {
                    "nl": "Ik zou de wachtregel die je beschrijft niet alleen uit angst voor een gemiste beweging negeren. Schrijf op wat voor jou bevestiging betekent en wacht met handelen totdat je die kunt controleren. Welke concrete voorwaarde bedoel je?",
                    "en": "I wouldn't ignore the wait rule you describe just because you fear missing a move. Write down what confirmation means to you and wait before acting until you can check it. What specific condition do you mean?",
                    "de": "Ich würde die von dir beschriebene Warteregel nicht nur aus Angst vor einer verpassten Bewegung ignorieren. Schreib auf, was für dich als Bestätigung zählt, und warte mit dem Handeln, bis du es prüfen kannst. Welche konkrete Bedingung meinst du?",
                }[language]
            return {
                "nl": "De angst om een koersbeweging te missen maakt rustig beslissen lastig. Schrijf eerst op wat voor jou een geldige aanleiding is om te handelen en wacht met een instap totdat je die kunt controleren. Welke concrete voorwaarde zou je willen gebruiken?",
                "en": "FOMO can make it hard to decide calmly. Write down what would justify acting, then check whether it has actually happened. What specific condition would you use?",
                "de": "FOMO kann eine ruhige Entscheidung erschweren. Schreib zuerst auf, was ein Handeln rechtfertigen würde, und prüfe, ob es wirklich eingetreten ist. Welche konkrete Bedingung würdest du verwenden?",
            }[language]
        if re.search(r"\b(?:frustrat\w*|gefrustreerd|frustrerend|ongeduldig|stressed?|gestrest|ärger\w*)\b", message, re.I):
            return {
                "nl": "Dat klinkt frustrerend. Laten we eerst scheiden wat je weet van wat je vermoedt. Welke beslissing wil je nemen, en welke informatie heb je nodig om die rustig te beoordelen?",
                "en": "That sounds frustrating. Let's separate what you know from what you suspect. What decision are you facing, and what information would help you assess it calmly?",
                "de": "Das klingt frustrierend. Lass uns trennen, was du weißt, von dem, was du vermutest. Welche Entscheidung steht an, und welche Information brauchst du dafür?",
            }[language]
        return None

    @staticmethod
    def _stop_loss_coach_fallback(locale: str | None) -> str:
        return {
            "nl": "Ik zou een stop-loss niet uit angst voor uitstopping weghalen. Pauzeer eerst en controleer welke maximale verliesgrens je vooraf had gekozen; zonder dat plan kan ik geen veilig nieuw niveau aanwijzen. Ik wijzig niets. Welke reden had je destijds voor deze grens?",
            "en": "I wouldn't remove a stop-loss just because you're afraid of being stopped out. Pause and check the maximum loss you planned beforehand; without that plan I can't name a safe replacement level. I won't change anything. Why did you choose that limit?",
            "de": "Ich würde einen Stop-Loss nicht aus Angst vor dem Ausstoppen entfernen. Halte erst inne und prüfe, welche Verlustgrenze du zuvor festgelegt hast; ohne diesen Plan kann ich kein sicheres neues Niveau nennen. Ich ändere nichts. Warum hast du diese Grenze gewählt?",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @classmethod
    def recover_read_only_coaching(
        cls, *, message: str, result: FinnResponsesResult,
        answer: FinnResponsesVerifiedAnswer, locale: str | None,
    ) -> FinnResponsesVerifiedAnswer:
        """Keep process coaching usable when a model draft cannot be verified.

        The fallback makes no account or market claim and is available only
        after the normal answer and bounded read repair have failed.
        """
        if answer.status != "unavailable" or not result.model_led_coach:
            return answer
        if any(
            "_proposal" in str(call.get("name") or "")
            or (call.get("result") or {}).get("proposal_id")
            for call in result.tool_trace
        ):
            return answer
        if _read_only_stop_loss_coaching(message):
            return FinnResponsesVerifiedAnswer(
                "completed", cls._stop_loss_coach_fallback(locale),
                "safe_stop_loss_coaching", answer.evidence,
                answer.used_previous_response,
            )
        return answer

    @staticmethod
    def _hypothetical_reflection_fallback(locale: str | None) -> str:
        return {
            "nl": "In je hypothetische voorbeeld is impulsief handelen het patroon om te onderzoeken; de negatieve uitkomst bewijst op zichzelf geen oorzaak. Test volgende week één regel: schrijf vóór elke trade een concrete instapvoorwaarde en je maximale risico op, en sla de trade over als die ontbreken. Dit is geen opgeslagen tradehistorie.",
            "en": "In your hypothetical example, impulsive trading is the pattern to examine; the negative outcome alone does not prove a cause. Test one rule next week: write down a concrete entry condition and your maximum risk before each trade, and skip it if either is missing. This is not saved trade history.",
            "de": "In deinem hypothetischen Beispiel ist impulsives Handeln das Muster, das du untersuchen solltest; das negative Ergebnis allein beweist keine Ursache. Teste nächste Woche eine Regel: Notiere vor jedem Trade eine konkrete Einstiegsbedingung und dein maximales Risiko und verzichte auf den Trade, wenn eines davon fehlt. Das ist keine gespeicherte Handelshistorie.",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @staticmethod
    def _saved_confirmation_answer(
        message: str, evidence: tuple[dict[str, Any], ...], locale: str | None,
    ) -> str | None:
        if not _saved_confirmation_readback(message):
            return None
        setup_read = next((
            item["data"] for item in evidence
            if item.get("scope") == "read_active_setup" and item.get("status") == "completed"
            and isinstance(item.get("data"), dict) and item["data"].get("setup_id")
        ), None)
        if not setup_read:
            return None
        timeframe = re.search(r"\b(?:1H|4H|1D|1W|15M|30M)\b", message, re.I)
        assets = mentioned_catalog_symbols(message)
        collection = setup_read.get("setups")
        matching = [
            row for row in collection if isinstance(row, dict) and row.get("name")
            and (not timeframe or str(row.get("timeframe") or "").casefold() == timeframe.group().casefold())
            and (not assets or str(row.get("symbol") or "").upper() in assets)
        ] if isinstance(collection, list) else []
        if len(matching) > 1:
            names = ", ".join(f"‘{row['name']}’" for row in matching[:4])
            return {
                "nl": f"Ik zie meerdere passende opgeslagen setups: {names}. Welke bedoel je? Dan kan ik de bevestigingsvoorwaarde van die specifieke setup controleren.",
                "en": f"I can see multiple matching saved setups: {names}. Which one do you mean? I can then check that setup's confirmation condition.",
                "de": f"Ich sehe mehrere passende gespeicherte Setups: {names}. Welches meinst du? Dann kann ich die Bestätigungsregel dieses Setups prüfen.",
            }[locale if locale in {"nl", "en", "de"} else "nl"]
        if len(matching) == 1 and matching[0].get("setup_id") != setup_read.get("setup_id"):
            name = str(matching[0]["name"])
            return {
                "nl": f"De passende setup heet ‘{name}’. De huidige readback hoort bij een andere setup, dus ik kan de bevestigingsvoorwaarde van ‘{name}’ nog niet betrouwbaar aanwijzen. Vraag me gericht naar die setup.",
                "en": f"The matching setup is ‘{name}’. The current readback is for a different setup, so I cannot reliably identify the confirmation condition of ‘{name}’ yet. Ask me about that setup by name.",
                "de": f"Das passende Setup heißt ‘{name}’. Die aktuelle Abfrage betrifft ein anderes Setup, daher kann ich die Bestätigungsregel von ‘{name}’ noch nicht zuverlässig nennen. Frage mich gezielt nach diesem Setup.",
            }[locale if locale in {"nl", "en", "de"} else "nl"]
        selected_name = str(matching[0]["name"] if len(matching) == 1 else setup_read.get("name") or "").strip()
        if any(
            item.get("status") == "completed"
            and item.get("scope") in {"read_active_setup", "read_linked_strategy"}
            and isinstance(item.get("data"), dict)
            and any(item["data"].get(key) for key in (
                "confirmation_condition", "entry_condition", "entry_conditions",
                "confirmation_rule", "entry_rule", "trigger_conditions",
            ))
            for item in evidence
        ):
            return None
        label = f"‘{selected_name}’" if selected_name else "de gelezen setup"
        return {
            "nl": f"Ik bedoel {label}. In de gegevens die ik voor deze opgeslagen setup kan lezen staat geen concrete bevestigings- of entryregel. Ik kan daarom geen bestaande voorwaarde aanwijzen; je kunt er eerst een meetbare formuleren voordat je die als instapcheck gebruikt.",
            "en": f"I mean {label}. The saved setup data I can read contains no specific confirmation or entry rule. I can't point to an existing condition; you could first define a measurable one before using it as an entry check.",
            "de": f"Ich meine {label}. In den Daten, die ich zu diesem gespeicherten Setup lesen kann, steht keine konkrete Bestätigungs- oder Einstiegsregel. Ich kann deshalb keine vorhandene Bedingung nennen; du könntest zuerst eine messbare Regel festlegen, bevor du sie als Einstiegskriterium nutzt.",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @staticmethod
    def _grounded_plan_review_fallback(
        message: str, evidence: tuple[dict[str, Any], ...], locale: str | None,
    ) -> str | None:
        if not (
            re.search(r"\b(?:beoordeel|review|bewerte)\b", message, re.I)
            and re.search(r"\b(?:plan|strategie|strategy|Strategie)\b", message, re.I)
        ):
            return None
        strategy = next((
            item.get("data") for item in evidence
            if item.get("scope") == "read_linked_strategy"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and all(item["data"].get(field) for field in ("entry", "stop_loss", "targets"))
        ), None)
        if strategy is None:
            return None
        return {
            "nl": "Sterk: je opgeslagen strategie bevat een entry, stop-loss en doelen, zodat je de risicoafstand kunt controleren. Waar ik je afrem: die planwaarden tonen niet of er nu een geldige instap is en evenmin of het risico bij jou past. Eerstvolgende check: leg een concrete instapvoorwaarde vast en controleer die met verifieerbare actuele gegevens voordat je een positie overweegt.",
            "en": "Strength: your saved strategy has an entry, stop-loss and targets, so you can check the risk distance. Where I'd slow you down: those plan values do not show whether an entry is valid now or whether the risk suits you. Next check: define a specific entry condition and verify it against current evidence before considering a position.",
            "de": "Stärke: Deine gespeicherte Strategie enthält Einstieg, Stop-Loss und Ziele, sodass du den Risikoabstand prüfen kannst. Wo ich dich bremsen würde: Diese Planwerte zeigen weder einen aktuell gültigen Einstieg noch, ob das Risiko zu dir passt. Nächster Check: Lege eine konkrete Einstiegsbedingung fest und prüfe sie anhand aktueller verlässlicher Daten, bevor du eine Position erwägst.",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @staticmethod
    def _limited_personal_plan_fallback(
        message: str, evidence: tuple[dict[str, Any], ...],
        tool_trace: tuple[dict[str, Any], ...], locale: str | None,
    ) -> str | None:
        if not any(
            call.get("name") == "evaluate_plan"
            and (call.get("result") or {}).get("assessment_status") == "insufficient_evidence"
            for call in tool_trace
        ):
            return None
        profile = next((
            item.get("data") for item in evidence
            if item.get("scope") == "read_profile" and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
        ), None)
        setup = next((
            item.get("data") for item in evidence
            if item.get("scope") == "read_active_setup" and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
        ), None)
        if not profile or not setup or not setup.get("symbol"):
            return None
        language = locale if locale in {"nl", "en", "de"} else "nl"
        asset = str(setup.get("symbol") or "").upper()
        amount = re.search(
            r"(?:€\s*)?(\d+(?:[.,]\d+)?)\s*(?:euro|euros|eur|€)\s*"
            r"(?:per\s+week|a\s+week|weekly|pro\s+woche)", message, re.I,
        )
        weekly_dca = (
            amount is not None and setup.get("setup_type") == "dca"
            and re.search(r"\b(?:dca|dagelijks|daily|täglich)\b", message, re.I)
        )
        if weekly_dca:
            proposed = amount.group(1)
            return {
                "nl": f"Je overweegt €{proposed} per week voor {asset}-DCA; dat is jouw voorstel, geen opgeslagen wijziging. Je profiel en DCA-setup zijn gelezen, maar ik kan niet beoordelen of dit bij je risicostijl past zonder je huidige totale inleg en een volledige risicobeoordeling. Controleer eerst of €{proposed} per week je totale {asset}-inleg verhoogt of ongeveer gelijk houdt. Welke van die twee bedoel je?",
                "en": f"You're considering €{proposed} per week for {asset} DCA; that is your proposal, not a saved change. I can read your profile and DCA setup, but cannot judge whether it fits your risk style without your current total contribution and a full risk assessment. First check whether €{proposed} per week raises your total {asset} contribution or keeps it roughly level. Which do you mean?",
                "de": f"Du erwägst €{proposed} pro Woche für {asset}-DCA; das ist dein Vorschlag, keine gespeicherte Änderung. Ich kann dein Profil und DCA-Setup lesen, aber ohne deine bisherige Gesamteinzahlung und eine vollständige Risikoprüfung nicht beurteilen, ob das zu deinem Risikostil passt. Prüfe zuerst, ob €{proposed} pro Woche deine gesamte {asset}-Einzahlung erhöht oder ungefähr gleich hält. Was meinst du?",
            }[language]
        if not re.search(r"\b(?:beoordeel|assess|bewerte)\b", message, re.I):
            return None
        return {
            "nl": f"Ik kan je volledige {asset}-plan nog niet als passend bij je risicostijl beoordelen. Je profiel en opgeslagen setup zijn gelezen, maar de evaluatie meldt ontbrekende gegevens voor een volledig oordeel. Controleer eerst je totale inleg en de maximale verliesgrens die je wilt hanteren; deze beperkte beoordeling geeft geen instapsignaal.",
            "en": f"I can't yet judge whether your full {asset} plan fits your risk style. I can read your profile and saved setup, but the evaluation lacks evidence for a full judgment. First check your total contribution and the maximum loss you intend to accept; this limited review is not an entry signal.",
            "de": f"Ich kann noch nicht beurteilen, ob dein vollständiger {asset}-Plan zu deinem Risikostil passt. Dein Profil und gespeichertes Setup sind lesbar, aber der Bewertung fehlen Daten für ein vollständiges Urteil. Prüfe zuerst deine Gesamteinzahlung und die Verlustgrenze, die du akzeptieren willst; diese begrenzte Prüfung ist kein Einstiegssignal.",
        }[language]

    @staticmethod
    def _rule_objection_answer(
        message: str, previous_answer: str, locale: str | None,
    ) -> str | None:
        if not _rule_objection(message, previous_answer):
            return None
        return {
            "nl": "Ik snap je bezwaar: een regel die te streng voelt, mag je kritisch bekijken. Een strenge wachttijd is niet vanzelf veiliger, maar versoepelen uit ongeduld is ook geen onderbouwde keuze. Kijk welk risico de regel moest begrenzen en welke meetbare voorwaarde datzelfde doel dient. Gaat je bezwaar vooral over de wachttijd of over het vereiste signaal?",
            "en": "I hear your objection: a rule that feels too strict is worth reviewing. A longer wait is not automatically safer, but relaxing it out of impatience is not a reasoned choice either. Check what risk the rule was meant to limit and what measurable condition would serve that purpose. Is your objection mainly about the wait or the required signal?",
            "de": "Ich verstehe deinen Einwand: Eine Regel, die zu streng wirkt, solltest du prüfen. Längeres Warten ist nicht automatisch sicherer, aber die Regel aus Ungeduld zu lockern ist auch keine begründete Entscheidung. Prüfe, welches Risiko sie begrenzen sollte und welche messbare Bedingung denselben Zweck erfüllt. Geht es dir vor allem um die Wartezeit oder um das verlangte Signal?",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @staticmethod
    def _unsupported_personal_confirmation(
        answer: str, evidence: tuple[dict[str, Any], ...], message: str = "",
    ) -> bool:
        if (
            _hypothetical_trade_reflection(message)
            and not re.search(r"\b(?:opgeslagen|bewaarde|saved|gespeichert\w*)\b", answer, re.I)
            and not re.search(
                r"\b(?:je|jouw)\s+bevestigingsvoorwaarde\s+(?:is|staat|luidt|vereist)\b|"
                r"\byour\s+confirmation\s+condition\s+(?:is|requires|says)\b|"
                r"\bdeine\s+Bestätigungsbedingung\s+(?:ist|lautet|verlangt)\b",
                answer, re.I,
            )
        ):
            return False
        answer = re.sub(r"[*_`]", "", answer)
        if not re.search(
            r"\b(?:jouw|je)\s+bevestigingsvoorwaarde\b|\byour\s+confirmation\s+condition\b|"
            r"\bdeine\s+Bestätigungsbedingung\b", answer, re.I,
        ):
            return False
        for item in evidence:
            if item.get("status") != "completed" or item.get("scope") not in {"read_active_setup", "read_linked_strategy"}:
                continue
            data = item.get("data") or {}
            if not isinstance(data, dict):
                continue
            if any(data.get(key) for key in (
                "confirmation_condition", "entry_condition", "entry_conditions",
                "confirmation_rule", "entry_rule", "trigger_conditions",
            )):
                return False
        return True

    @staticmethod
    def _model_led_repair_instructions(locale: str | None) -> str:
        language = {"nl": "Dutch", "en": "English", "de": "German"}.get(locale or "", "Dutch")
        return (
            f"You are FINN. Answer entirely in {language}. Rewrite the rejected answer using "
            "only the current question, typed FINN evidence, registry operations and previous "
            "verified answer. Answer the current question rather than repeating the previous "
            "visible answer; that answer is context, not a template. The rejected draft is "
            "not evidence. Remove every claim identified "
            "by rejection_reasons; do not merely paraphrase it. A completed read proves only the "
            "fields returned by that read. Missing transaction, market or account data in a "
            "different scope must not be presented as absent from the user's account. A typed "
            "*_not_resolved result permits 'I cannot identify it uniquely', not 'it does not exist'. "
            "A capability absent from registered_operations cannot be performed; this does not "
            "imply a provider outage. Do not invent saved facts, current prices, financial outcomes, "
            "writes or executions. Never propose an automatic broker order or live-bot activation. "
            "Give one concise useful answer or one targeted follow-up question. Hide IDs and codes."
            " If the rejection concerns bypassing a user-stated precaution, remove any"
            " conditional workaround for bypassing it; an exit plan does not establish"
            " that the missing confirmation has occurred, and a smaller position does not"
            " satisfy an unmet entry condition."
            " If unverified_personal_claim is rejected, do not replace it with"
            " a softer claim about suitability, plan quality, risk tolerance or likely"
            " returns. State which assessment remains unsupported, distinguish known"
            " saved facts from judgments, and offer one concrete safe next step."
            " When a classification or suitability conclusion depends on a user choice that is"
            " neither saved nor stated, do not infer it from an adjacent field such as chart"
            " timeframe or general investment goal. Ask for that choice directly; do not"
            " replace the question with a generic lack-of-evidence refusal."
            " If saved_entity_type_not_supported appears in rejection_reasons, do not refer"
            " to an unavailable linked object as the user's saved object. You may explain"
            " that it was not found or speak hypothetically about creating one later."
        )

    @staticmethod
    def _language_matches(text: str, locale: str | None) -> bool:
        if locale not in {"nl", "en", "de"}:
            return True
        if locale != "en" and re.search(
            r"\b(?:unassessed|unverified|unavailable)\b", text, re.IGNORECASE,
        ):
            return False
        DetectorFactory.seed = 0
        for sentence in re.split(r"(?<!\d)[.!?](?!\d)|\n+", text):
            word_count = len(sentence.split())
            if word_count < 5:
                continue
            label, separator, _value = sentence.partition(":")
            if separator and len(label.split()) <= 3 and word_count <= 12:
                # A saved name or ticker after a short field label is data, not prose.
                continue
            try:
                candidate = detect_langs(sentence)[0]
            except LangDetectException:
                continue
            # Short sentences need stronger confidence because names and tickers skew detection.
            if word_count < 8 and candidate.prob < 0.95:
                continue
            # langdetect frequently labels short Dutch sentences as Afrikaans;
            # this is not evidence that the user-facing text changed language.
            if locale == "nl" and candidate.lang == "af":
                continue
            if candidate.lang != locale and (
                candidate.lang in {"nl", "en", "de"} or candidate.prob >= 0.95
            ):
                return False
        return True

    @staticmethod
    def _profile_presence_claim_supported(text: str, evidence: tuple[dict[str, Any], ...]) -> bool:
        has_saved_risk_profile = any(
            item.get("scope") == "read_profile"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and bool((item["data"].get("trader_profile") or {}).get("risk_profiles"))
            for item in evidence
        )
        if not has_saved_risk_profile:
            return True
        missing_profile_claims = (
            r"(?:risicoprofiel|risicostijl|risico-instellingen)\s+(?:ontbreekt|ontbreken|missen)",
            r"\bgeen\s+opgeslagen\s+(?:(?:feiten|gegevens|informatie)\s+(?:over\s+)?(?:je|jouw|het)\s+)?risicoprofiel\b",
            r"(?:geen|zonder)\s+(?:volledig\s+)?inzicht\s+(?:hebben\s+)?in\s+(?:je|jouw|het)\s+(?:risicoprofiel|risicostijl)",
            r"(?:risk profile|risk style|risk settings)\s+(?:is|are)\s+(?:missing|not available|unknown)",
            r"(?:no|without)\s+insight\s+into\s+(?:your|the)\s+(?:risk profile|risk style)",
            r"(?:missing|lack(?:ing)?)\s+(?:your\s+)?(?:risk profile|risk style|risk settings)",
            r"(?:risikoprofil|risikoeinstellungen|risikostil)\s+(?:fehlt|fehlen)",
            r"(?:informationen|angaben)\s+über\s+(?:dein(?:e|en)?|das)\s+"
            r"(?:risikoeinstellung|risikoprofil|risikostil)[^.!?]{0,65}"
            r"(?:fehl\w*|nicht\s+verfügbar|unbekannt)",
            r"(?:kein|ohne)\s+einblick\s+in\s+(?:dein|das)\s+risikoprofil",
            r"(?:fehlend(?:e|en|er|es)?|ohne)\s+(?:\w+\s+){0,2}(?:risikoprofil|risikoeinstellungen|risikostil)",
        )
        return not any(re.search(pattern, text.casefold()) for pattern in missing_profile_claims)

    @staticmethod
    def _saved_horizon_claim_supported(text: str, evidence: tuple[dict[str, Any], ...]) -> bool:
        saved_objects = [
            item.get("data") for item in evidence
            if item.get("status") == "completed"
            and item.get("scope") in {"read_active_setup", "read_linked_strategy"}
            and isinstance(item.get("data"), dict)
        ]
        if not saved_objects or any(
            data.get(field) for data in saved_objects
            for field in ("investment_horizon", "holding_period", "trade_horizon")
        ):
            return True
        inferred_horizon = (
            r"(?:langetermijn\w*|lange termijn|kortetermijn\w*|swingtrade|swing trade|"
            r"long.term|short.term|swing.trading|accumulation|opbouw|"
            r"langfristig\w*|kurzfristig\w*|vermögensaufbau)"
        )
        # A negated category is not an asserted holding horizon. Keep other
        # categories in the sentence so a positive inference still fails.
        text_for_horizon = re.sub(
            r"\b(?:geen|not(?:\s+a)?|kein(?:e|en|er|es)?)\s+swing.?trad\w*\b",
            "", text, flags=re.IGNORECASE,
        )
        return not any(
            re.search(
                r"\b(?:je|jouw|mijn|your|my|dein(?:e|er|es)?|mein(?:e|er|es)?)\b"
                r"[^.!?\n]{0,55}\b(?:setup|plan|strategie|strategy)\b"
                r"[^.!?\n]{0,75}\b(?:is|betreft|leunt|gericht|lijkt\s+bedoeld\s+voor|richt\s+zich\s+op|means|appears\s+intended\s+for|is geared|is aimed|"
                r"ist|zielt|deutet|wijst|suggests|indicates)\b"
                rf"[^.!?\n]{{0,85}}\b{inferred_horizon}\b",
                sentence, re.IGNORECASE,
            )
            or re.search(
                r"\b(?:setup|plan|strategie|strategy)\b[^.!?\n]{0,110}"
                r"\b(?:structured\s+as|opgebouwd\s+als|strukturiert\s+als)\b"
                rf"[^.!?\n]{{0,80}}\b{inferred_horizon}\b",
                sentence, re.IGNORECASE,
            )
            or re.search(
                r"\b(?:setup|plan|strategie|strategy)\b[^.!?\n]{0,100}"
                r"\b(?:eignet\s+sich|is\s+suited|is\s+gericht|geschikt\s+voor|past|passt|ist\s+darauf\s+ausgelegt)\b"
                rf"[^.!?\n]{{0,105}}\b{inferred_horizon}\b",
                sentence, re.IGNORECASE,
            )
            or re.search(
                r"\b(?:dies|das|es|this|that|dit|dat)\b[^.!?\n]{0,45}"
                r"\b(?:deutet|suggests|indicates|aligns|points|tends|wijst|past)\b[^.!?\n]{0,100}"
                rf"\b{inferred_horizon}\b",
                sentence, re.IGNORECASE,
            )
            or re.search(
                r"\b(?:hierdoor|daardoor|therefore|thus|dadurch|deshalb)\b[^.!?\n]{0,100}"
                r"\b(?:beschouwd\s+als|considered(?:\s+(?:as|to\s+be))?|angesehen\s+als|gilt\s+als)\b"
                rf"[^.!?\n]{{0,75}}\b{inferred_horizon}\b",
                sentence, re.IGNORECASE,
            )
            for sentence in re.split(r"(?<=[.!?])\s+", text_for_horizon)
        ) and not re.search(
            r"\b(?:dit|deze|het|this|it|das|dieses)\s+is\s+(?:geen|not|kein)\s+swing.?trad\w*\b"
            r"[^.!?\n]{0,90}\b(?:langetermijn\w*|long.term|langfristig\w*)\b",
            text, re.IGNORECASE,
        )

    @staticmethod
    def _fallback_language(message: str, previous_answer: str = "") -> str:
        DetectorFactory.seed = 0
        brief = message.strip().casefold().rstrip("?!. ")
        if brief in {"why", "how"}:
            return "en"
        if brief in {"warum", "wieso", "weshalb"}:
            return "de"
        if brief in {"waarom", "hoe"}:
            return "nl"
        for sample in (message, previous_answer):
            if not sample.strip():
                continue
            try:
                language = detect(sample)
            except LangDetectException:
                continue
            if language in {"nl", "en", "de"}:
                return language
        return "nl"

    @classmethod
    def _fallback_copy(cls, reason: str, *, message: str, previous_answer: str = "", locale: str | None = None) -> str:
        language = locale if locale in {"nl", "en", "de"} else cls._fallback_language(message, previous_answer)
        copies = {
            "setup_ambiguous": {
                "nl": "Ik zie meerdere setups. Welke wil je als uitgangspunt voor je plan gebruiken?",
                "en": "I found several setups. Which one should I use as the basis for your plan?",
                "de": "Ich sehe mehrere Setups. Welches soll ich als Grundlage für deinen Plan verwenden?",
            },
            "source_unavailable": {
                "nl": "Ik heb hiervoor geen betrouwbare actuele gegevens. Zonder die bron kan ik dit nog niet beoordelen.",
                "en": "I don't have reliable current data for this. Without that source, I can't assess it yet.",
                "de": "Mir fehlen dafür verlässliche aktuelle Daten. Ohne diese Quelle kann ich es noch nicht beurteilen.",
            },
            "previous_source_unavailable": {
                "nl": "Ik kan de oorzaak van de ontbrekende gegevens niet vaststellen. Daarom kan ik het effect op je plan nog niet betrouwbaar beoordelen.",
                "en": "I can't establish why the data is missing, so I can't reliably assess its effect on your plan yet.",
                "de": "Ich kann die Ursache der fehlenden Daten nicht feststellen und ihre Auswirkung auf deinen Plan daher noch nicht zuverlässig beurteilen.",
            },
            "limited_evaluation": {
                "nl": "Ik kan nog niet beoordelen of dit bij je risicostijl past: de benodigde actuele gegevens ontbreken. Ik zou je huidige instellingen op basis hiervan nog niet wijzigen.",
                "en": "I can't yet assess whether this fits your risk style because the required current data is missing. I wouldn't change your saved settings on this evidence alone.",
                "de": "Ich kann noch nicht beurteilen, ob das zu deinem Risikoprofil passt: Die nötigen aktuellen Daten fehlen. Auf dieser Grundlage würde ich deine gespeicherten Einstellungen noch nicht ändern.",
            },
            "evidence_limited": {
                "nl": "Ik kan dit met de beschikbare gegevens nog niet beoordelen. Er is niets gewijzigd.",
                "en": "I can't assess this from the available evidence yet. Nothing was changed.",
                "de": "Ich kann das mit den verfügbaren Daten noch nicht beurteilen. Es wurde nichts geändert.",
            },
            "responses_provider_timeout": {
                "nl": "Ik heb je gegevens opgehaald, maar kon het antwoord nu niet afronden. Er is niets gewijzigd. Probeer het zo opnieuw.",
                "en": "I retrieved your data but couldn't finish the answer just now. Nothing was changed. Please try again shortly.",
                "de": "Ich habe deine Daten abgerufen, konnte die Antwort aber gerade nicht abschließen. Es wurde nichts geändert. Bitte versuche es gleich noch einmal.",
            },
        }
        return copies.get(reason, {}).get(language) or {
            "nl": "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
            "en": "I can't support this with reliable evidence yet.",
            "de": "Ich kann das noch nicht mit verlässlichen Daten belegen.",
        }[language]

    @classmethod
    def _proposed_change_copy(cls, *, message: str, locale: str | None) -> str | None:
        proposal = re.search(
            r"(?:€\s*\d[\d.,]*|\d[\d.,]*\s*(?:euros?|eur|€))"
            r"\s*(?:(?:per|pro)\s+(?:week|woche|month|monat|maand|day|tag|dag))?",
            message, re.IGNORECASE,
        )
        proposed_intent = re.search(
            r"\b(?:denk\s+aan|overweeg|wil|considering|consider|thinking\s+of|"
            r"erwäge|überlege|möchte)\b",
            message, re.IGNORECASE,
        )
        if not proposal or not proposed_intent:
            return None
        amount = proposal.group().strip()
        language = locale if locale in {"nl", "en", "de"} else cls._fallback_language(message)
        return {
            "nl": f"Je overweegt {amount}.",
            "en": f"You are considering {amount}.",
            "de": f"Du erwägst {amount}.",
        }[language]

    @classmethod
    def _attribute_user_proposal(cls, *, answer: str, message: str, locale: str | None) -> str:
        if not re.search(r"\b(?:past|passen|fit|fits|suit|suits|geeignet)\b", message, re.I):
            return answer
        proposal = cls._proposed_change_copy(message=message, locale=locale)
        if proposal is None or re.search(
            r"\b(?:je\s+(?:overweegt|denkt\s+aan)|jouw\s+voorstel|"
            r"you\s+(?:are\s+considering|propose)|your\s+proposal|"
            r"du\s+(?:erwägst|überlegst)|dein\s+Vorschlag)\b",
            answer, re.I,
        ):
            return answer
        return f"{proposal} {answer}"

    @classmethod
    def _limited_evaluation_copy(cls, *, message: str, locale: str | None) -> str:
        proposed = cls._proposed_change_copy(message=message, locale=locale)
        if proposed is None:
            return cls._fallback_copy("evidence_limited", message=message, locale=locale)
        language = locale if locale in {"nl", "en", "de"} else cls._fallback_language(message)
        return {
            "nl": f"{proposed} Ik kan nog niet beoordelen of die wijziging bij je risicostijl past: de benodigde actuele gegevens ontbreken. Je opgeslagen setup blijft ongewijzigd.",
            "en": f"{proposed} I can't yet assess whether that change suits your risk style because the required current data is missing. Your saved setup remains unchanged.",
            "de": f"{proposed} Ob diese Änderung zu deinem Risikoprofil passt, kann ich ohne die nötigen aktuellen Daten noch nicht beurteilen. Dein gespeichertes Setup bleibt unverändert.",
        }[language]

    @staticmethod
    def _horizon_clarification_copy(locale: str | None) -> str:
        return {
            "nl": "4H beschrijft het tijdsbestek van je grafiek, niet hoelang je wilt beleggen. Beoog je opbouw voor de lange termijn of kortere trades?",
            "en": "4H describes your chart timeframe, not how long you intend to invest. Are you aiming for long-term accumulation or shorter trades?",
            "de": "4H beschreibt den Zeitraum deines Charts, nicht deinen Anlagehorizont. Möchtest du langfristig Vermögen aufbauen oder eher kurzfristig handeln?",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @staticmethod
    def _user_detail_acknowledgement(message: str, locale: str | None) -> str:
        if message.startswith("Original user request:") and "User's chosen answer:" in message:
            message = message.rsplit("User's chosen answer:", 1)[1]
        detail = " ".join(message.split())[:120]
        return {
            "nl": f"Ik begrijp je antwoord: ‘{detail}’. Ik neem dit mee in ons gesprek, maar je opgeslagen plan is niet gewijzigd. Of het bij je past, kan ik zonder een actuele beoordeling nog niet zeggen.",
            "en": f"I understand your answer: ‘{detail}’. I'll use it in this conversation, but your saved plan has not changed. I can't judge whether it suits you without a current assessment.",
            "de": f"Ich verstehe deine Antwort: „{detail}“. Ich berücksichtige sie in diesem Gespräch, aber dein gespeicherter Plan wurde nicht geändert. Ob er zu dir passt, kann ich ohne aktuelle Beurteilung noch nicht sagen.",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @classmethod
    def _horizon_detail_acknowledgement(
        cls, message: str, evidence: tuple[dict[str, Any], ...], locale: str | None,
    ) -> str:
        if message.startswith("Original user request:") and "User's chosen answer:" in message:
            message = message.rsplit("User's chosen answer:", 1)[1]
        detail = " ".join(message.split())[:120].rstrip(".! ")
        setup = next((
            item.get("data") for item in evidence
            if item.get("scope") == "read_active_setup"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
        ), None)
        if not setup or setup.get("setup_type") != "dca":
            return cls._user_detail_acknowledgement(message, locale)
        return {
            "nl": f"Voor je DCA-setup geef je deze beleggingshorizon aan: ‘{detail}’. Dat neem ik mee in dit gesprek; je opgeslagen setup is niet gewijzigd. Of die setup bij je past, vraagt nog een aparte beoordeling.",
            "en": f"For your DCA setup, you've given this investment horizon: ‘{detail}’. I'll use that in this conversation; your saved setup has not changed. Whether it suits you still needs a separate assessment.",
            "de": f"Für dein DCA-Setup nennst du diesen Anlagehorizont: „{detail}“. Das berücksichtige ich in diesem Gespräch; dein gespeichertes Setup wurde nicht geändert. Ob es zu dir passt, muss noch gesondert beurteilt werden.",
        }[locale if locale in {"nl", "en", "de"} else "nl"]

    @staticmethod
    def _answered_duration_preserved(message: str, answer: str) -> bool:
        if "User's chosen answer:" not in message:
            return True
        chosen = message.rsplit("User's chosen answer:", 1)[1].casefold()
        number_words = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
            "een": "1", "twee": "2", "drie": "3", "vier": "4", "vijf": "5",
            "zes": "6", "zeven": "7", "acht": "8", "negen": "9", "tien": "10",
            "eins": "1", "zwei": "2", "drei": "3", "fünf": "5",
            "sechs": "6", "sieben": "7", "acht": "8", "neun": "9", "zehn": "10",
        }
        duration = re.search(
            r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"een|twee|drie|vier|vijf|zes|zeven|acht|negen|tien|"
            r"eins|zwei|drei|fünf|sechs|sieben|neun|zehn)\s+"
            r"(jaar|jaren|year|years|jahr|jahre|jahren)\b", chosen,
        )
        if not duration:
            return True
        expected = number_words.get(duration.group(1), duration.group(1))
        for match in re.finditer(
            r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"een|twee|drie|vier|vijf|zes|zeven|acht|negen|tien|"
            r"eins|zwei|drei|fünf|sechs|sieben|neun|zehn)\s+"
            r"(jaar|jaren|year|years|jahr|jahre|jahren)\b", answer.casefold(),
        ):
            if number_words.get(match.group(1), match.group(1)) == expected:
                return True
        return False

    @staticmethod
    def _typed_failure_reason(evidence: tuple[dict[str, Any], ...]) -> str:
        reasons = {
            str(item.get("reason") or "")
            for item in evidence if item.get("status") != "completed"
        }
        if "setup_ambiguous" in reasons:
            return "setup_ambiguous"
        unavailable_scopes = {
            str(item.get("scope")) for item in evidence
            if item.get("status") != "completed" and item.get("reason") == "source_unavailable"
        }
        if unavailable_scopes and not any(
            item.get("status") == "completed" and str(item.get("scope")) in unavailable_scopes
            for item in evidence
        ):
            return "source_unavailable"
        if evidence and all(item.get("status") != "completed" for item in evidence):
            return "source_unavailable"
        if not evidence:
            return "no_evidence_available"
        return "responses_evidence_not_verified"

    @staticmethod
    def _contains_internal_identifier(text: str) -> bool:
        return bool(re.search(r"\b[a-z]+(?:_[a-z0-9]+)+\b", text)) or bool(re.search(
            r"\bfinn-v2-(?:run|conv|proposal|execution|contract)-[\w-]+\b"
            r"|\b(?:setup|strategy|bot|proposal|execution|run)[\s_-]*id[*_`\s]*[:#=]",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _promises_unverified_trading_outcome(text: str) -> bool:
        probability_claim = re.compile(
            r"\b(?:kans|chance|probability|gewinnchance)\b.{0,55}\b"
            r"(?:succes|success|profit|winst|gewinn)\w*\b",
            re.IGNORECASE | re.DOTALL,
        )
        for match in probability_claim.finditer(text):
            prefix = re.split(r"[.!?;\n]|\b(?:maar|but|aber)\b", text[:match.start()], flags=re.I)[-1]
            if not re.search(
                r"\b(?:geen|no|not|kein\w*)\s+(?:(?:a|an)\s+)?(?:(?:betrouwbare|reliable|verlässliche)\s+)?"
                r"(?:beoordeling|inschatting|oordeel|uitspraak|bewijs|assessment|estimate|"
                r"judgment|evidence|Bewertung|Einschätzung|Aussage)\b[^.!?;\n]{0,50}$",
                prefix, re.I,
            ):
                return True
        return bool(re.search(
            r"\b(?:risic\w*|risk\w*|verlust\w*|loss\w*)\b.{0,40}\b"
            r"(?:beperk\w*|verminder\w*|verklein\w*|reduc\w*|lower\w*|senk\w*)\b"
            r"|\b(?:beperk\w*|verminder\w*|verklein\w*|reduc\w*|lower\w*|senk\w*)\b"
            r".{0,40}\b(?:risic\w*|risk\w*|verlust\w*|loss\w*)\b",
            text, re.IGNORECASE | re.DOTALL,
        )) or bool(re.search(
            r"\b(?:verlies voorkomen|verliezen vermijden|prevent losses|avoid losses|"
            r"verluste vermeiden|verluste verhindern|"
            r"verliezen.{0,30}vermijd\w*|"
            r"voorkom\w* dat je (?:in )?een ongunstige positie|"
            r"verhoog\w* (?:de )?kans|"
            r"increases? the chance)\b",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _strategy_levels_attributed_to_setup(
        text: str, evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        if not any(item.get("scope") == "read_active_setup" and item.get("status") == "completed" for item in evidence):
            return False
        if not any(item.get("scope") == "read_linked_strategy" and item.get("status") == "completed" for item in evidence):
            return False
        for sentence in re.split(r"[.!?\n]+", text):
            match = re.search(
                r"\bsetup\b[^.!?\n]{0,100}\b(?:met|heeft|with|has|enthält)\b"
                r"(?P<detail>[^.!?\n]{0,100})",
                sentence, re.IGNORECASE,
            )
            if not match:
                continue
            detail = match.group("detail")
            if re.search(r"\b(?:strategie|strategy|strategieplan)\b", match.group(0), re.IGNORECASE):
                continue
            if re.search(r"\b(?:entry|instap|einstieg|stop.?loss|targets?|doelen|ziele)\b", detail, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _saved_entity_type_supported(
        text: str, evidence: tuple[dict[str, Any], ...], *, user_message: str = "",
    ) -> bool:
        has_setup = any(item.get("scope") == "read_active_setup" and item.get("status") == "completed"
                        for item in evidence)
        has_strategy = any(item.get("scope") == "read_linked_strategy" and item.get("status") == "completed"
                           for item in evidence)
        if has_strategy:
            return True
        if not has_setup and re.search(
            r"\b(?:my|mijn|meine|meinen)\s+(?:saved |opgeslagen |gespeicherte )?strateg(?:ie|y)\b",
            user_message, re.IGNORECASE,
        ):
            return True
        # A saved setup must never be relabeled as a saved strategy when the
        # linked-strategy read did not find one. This validates a fact, not intent.
        saved_strategy_claim = (
            r"\b(?:je hebt|jij hebt|you have|du hast|sie haben)\s+"
            r"(?:een|an|eine)\s+(?:(?!setup\b|geen\b|no\b|keine\b|ohne\b)\w+[ -]+){0,5}"
            r"(?:dca[- ]?)?strateg(?:ie|y)\b"
            r"|\b(?:jouw|uw|your|dein(?:e|er|em|en|es)?|ihr(?:e|er|em|en|es)?)\s+"
            r"(?:(?:opgeslagen|huidige|actieve|saved|current|active|gespeicherte|aktuelle|aktive)\s+)?"
            r"(?:dca[- ]?)?strateg(?:ie|y)\b"
            r"|\b(?:je|jouw|your|dein(?:e)?)\s+[^.!?;\n]{0,25}"
            r"\bplan\b[^.!?;\n]{0,35}\b(?:gebaseerd op|based on|basiert auf)\s+"
            r"(?:een|a|eine)?\s*dca[- ]?strateg(?:ie|y)\b"
            r"|\b(?:plan|setup)\s+(?:is|betreft|ist|is)\s+(?:een|an|eine)\b"
            r"[^.!?;\n]{0,35}\b(?:dca[- ]?)?strateg(?:ie|y)\b"
            r"|\b(?:plan|setup)\b[^.!?;\n]{0,55}"
            r"\b(?:involves|includes|has|bevat|omvat|umfasst|enthält)\b"
            r"[^.!?;\n]{0,70}\bstrateg(?:ie|y)\b"
        )
        return not bool(re.search(saved_strategy_claim, text, re.IGNORECASE))

    @staticmethod
    def _introduces_new_catalog_option(
        text: str, previous_answer: str, evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        answer_text = text.casefold()
        previous_text = previous_answer.casefold()
        for item in evidence:
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            options = data.get("supported_options")
            if not isinstance(options, list):
                continue
            for option in options:
                if not isinstance(option, dict):
                    continue
                labels = {
                    str(option.get(key) or "").strip().casefold()
                    for key in ("name", "display_name")
                }
                if any(
                    len(label) >= 3 and label in answer_text and label not in previous_text
                    for label in labels
                ):
                    return True
        return False

    @staticmethod
    def _evaluation_presentation_is_coaching(
        text: str, *, requested_list: bool = False,
    ) -> bool:
        if requested_list:
            return True
        return not re.search(r"(?m)^\s*(?:#{1,6}\s|(?:[-*]|\d+[.)])\s)", text)

    @staticmethod
    def _factual_score_list_requested(message: str, evidence: tuple[dict[str, Any], ...]) -> bool:
        facts = FinnV2RequestPreprocessorService().preprocess(message=message)
        return (
            facts.primary_entity == "scores"
            and facts.action_polarity == "read"
            and facts.discourse_act == "information_request"
            and any(item.get("scope") == "read_asset_scores" and item.get("status") == "completed"
                    for item in evidence)
        )

    @staticmethod
    def _avoids_internal_user_frame(text: str) -> bool:
        return not bool(re.search(
            r"\b(?:de gebruiker\s+(?:wil|vraagt|heeft gevraagd)|"
            r"the user\s+(?:wants|asks|asked)|"
            r"der nutzer\s+(?:möchte|fragt)|die nutzerin\s+(?:möchte|fragt))\b",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _reoffers_attempted_evaluation(text: str) -> bool:
        return bool(re.search(
            r"\b(?:wil\s+je|zal\s+ik|zullen\s+we|would\s+you\s+like|shall\s+i|"
            r"möchtest\s+du|soll\s+ich)\b[^?!.]{0,160}\b"
            r"(?:[a-zäöü-]{0,24})?(?:beoordel\w*|evaluat\w*|assessment\w*|bewert\w*)\b",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _asks_user_to_supply_unavailable_source(text: str) -> bool:
        return bool(re.search(
            r"\b(?:vraag|verzoek|lever|zoek|request|provide|obtain|ask for|fordere|besorge|liefere)\b"
            r"[^.!?\n]{0,90}\b(?:marktdata|marktgegevens|marktanalyse|market data|market snapshot|"
            r"market analysis|marktdaten|marktanalyse)\b",
            text, re.IGNORECASE,
        ) or re.search(
            r"\b(?:als|indien|if|wenn)\s+(?:je|jij|you|du)\s+(?:meer\s+|more\s+|weitere\s+)?"
            r"(?:feiten|gegevens|informatie|facts|data|information|fakten|daten|informationen)\b"
            r"[^.!?\n]{0,80}\b(?:markt|market|koers|price|börse|kurs)\w*",
            text, re.IGNORECASE,
        ) or re.search(
            r"\b(?:update\w*|actualiseer\w*|ververs\w*|refresh\w*|aktualisier\w*)\b"
            r"[^.!?\n]{0,85}\b(?:markt|market|technisch|technical|markt|technisch)\w*"
            r"[^.!?\n]{0,35}\b(?:data|gegevens|snapshot|daten)\b",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _uses_unavailable_live_source_as_current_action(text: str) -> bool:
        for sentence in re.split(r"[.!?;\n]+", text):
            current_source_action = re.search(
                r"\b(?:controleer|vergelijk|evalueer|bekijk|bevestig|volg|monitor|houd|"
                r"check|compare|evaluate|review|"
                r"confirm|track|watch|prüfe|vergleiche|bewerte|bestätige|beobachte)\b"
                r"[^.!?;\n]{0,110}"
                r"\b(?:prijs|koers|markt|indicator|price|market|kurs|indikator)\w*\b",
                sentence, re.IGNORECASE,
            )
            waits_for_availability = re.search(
                r"\b(?:zodra|wanneer|als|when|once|sobald|wenn)\b[^.!?;\n]{0,75}"
                r"\b(?:beschikbaar|available|verfügbar)\b",
                sentence, re.IGNORECASE,
            )
            if current_source_action and not waits_for_availability:
                return True
        return False

    @staticmethod
    def _followup_advances_conversation(message: str, previous_answer: str, text: str) -> bool:
        short_why = message.strip().casefold().rstrip("?!. ") in {
            "waarom", "why", "warum", "wieso", "weshalb",
        }
        if not short_why or not previous_answer:
            return True
        return SequenceMatcher(
            None, previous_answer.casefold(), text.casefold(),
        ).ratio() < 0.8

    @staticmethod
    def _unevaluated_positive_fit_claim(text: str) -> bool:
        return bool(re.search(
            r"\b(?:past|sluit)\s+(?:goed|prima|uitstekend|perfect)\s+(?:bij|aan\s+bij)\b"
            r"|\b(?:past|passen|lijkt|lijken)\b[^.!?;\n]{0,100}\bgoed\s+(?:te\s+)?passen\s+bij\b"
            r"|\bpast\b[^.!?;\n]{0,65}\bgoed\s+bij\b"
            r"|\bsolide\s+aanpak\s+voor\b[^.!?;\n]{0,65}\b(?:risico|risk|risiko)"
            r"|\b(?:kan|zou)\b[^.!?;\n]{0,65}\b(?:acceptabel|passend|geschikt)\s+(?:zijn|kunnen\s+zijn)\b"
            r"|\b(?:fits|suits|aligns)\s+(?:(?:well|perfectly|closely)\s+)?(?:with|to)\b"
            r"|\b(?:may|might|could)\b[^.!?;\n]{0,65}\b(?:be\s+)?(?:acceptable|suitable)\b"
            r"|\bpasst\s+(?:gut|perfekt)\s+zu\b"
            r"|\bkönnte\b[^.!?;\n]{0,120}\b(?:vermögensaufbau|swing.trading)\b"
            r"[^.!?;\n]{0,90}\bunterstütz\w*\b",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _ungrounded_level_advice(text: str) -> bool:
        ratio_praise = re.search(
            r"\b(?:aantrekkelijk\w*|gunstig\w*|sterk\w*|goed\w*|positiev\w*|positief|beter|"
            r"attractive|favorable|favourable|good|strong|positive|better|attraktiv|günstig|gut|"
            r"positiv\w*|besser)\b[^.!?;\n]{0,100}"
            r"\b(?:risico.?opbrengst\w*|risico.?rendement\w*|risico.?beloning\w*|risk.?reward\w*|reward.?risk\w*|"
            r"verhouding\w*|ratio\w*|verhältnis\w*)\b"
            r"|\b(?:risico.?opbrengst\w*|risico.?rendement\w*|risico.?beloning\w*|risk.?reward\w*|reward.?risk\w*|"
            r"verhouding\w*|ratio\w*|verhältnis\w*)\b[^.!?;\n]{0,100}"
            r"\b(?:aantrekkelijk\w*|gunstig\w*|sterk\w*|goed\w*|positiev\w*|positief|beter|"
            r"attractive|favorable|favourable|good|strong|positive|better|attraktiv|günstig|gut|"
            r"positiv\w*|besser)\b",
            text, re.IGNORECASE,
        )
        directed_change = re.search(
            r"\b(?:stel|zet|activeer|plaats|set|adjust|change|activate|place|"
            r"setze|ändere|aktiviere)\b[^.!?;\n]{0,65}"
            r"\b(?:stop.?loss|target|doel|entry|instap|strategie|strategy|order)\b",
            text, re.IGNORECASE,
        )
        directed_change_by_pas = re.search(
            r"\bpas\b[^.!?;\n]{0,65}"
            r"\b(?:stop.?loss|target|doel|entry|instap|strategie|strategy|order)\b"
            r"[^.!?;\n]{0,30}\baan\b",
            text, re.IGNORECASE,
        )
        conditional_change = re.search(
            r"\b(?:pas\s+aan|adjust|change|ändere)\b[^.!?;\n]{0,65}"
            r"\b(?:doel|target|price|prijs|markt|market|ziel|preis)\b",
            text, re.IGNORECASE,
        )
        speculative_level_change = re.search(
            r"\b(?:bepaal|overweeg|consider|decide|entscheide|überlege)\b"
            r"[^.!?;\n]{0,100}\b(?:entry|instap|stop.?loss|target|doel|einstieg|ziel)\w*\b"
            r"[^.!?;\n]{0,70}\b(?:aanpass\w*|adjust\w*|chang\w*|änder\w*)\b",
            text, re.IGNORECASE,
        )
        trade_planning = re.search(
            r"\b(?:plan|overweeg|neem|take|planen|plane|nimm)\s+"
            r"(?:je\s+)?(?:winstneming\w*|profit.?tak\w*|gewinnmitnahme\w*)\b"
            r"|\b(?:winstneming\w*|profit.?tak\w*|gewinnmitnahme\w*)\b"
            r"[^.!?;\n]{0,20}\b(?:plannen|plan|overwegen|nemen|take|planen)\b",
            text, re.IGNORECASE,
        )
        return bool(ratio_praise or directed_change or directed_change_by_pas or conditional_change
                    or speculative_level_change or trade_planning)

    @staticmethod
    def _proposal_speaker_is_user(text: str) -> bool:
        return not bool(re.search(
            r"\b(?:ik\s+(?:denk\s+aan|overweeg|wil)|i\s+(?:am\s+considering|want)|"
            r"ich\s+(?:erwäge|überlege|möchte))\b[^.!?\n]{0,65}"
            r"(?:\d+[\d.,]*\s*(?:euro|eur|€)|€\s*\d+)",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _assistant_does_not_claim_user_mutation(text: str) -> bool:
        return not bool(re.search(
            r"\b(?:ik\s+wil|i\s+want\s+to|ich\s+möchte)\b"
            r"[^.!?\n]{0,90}\b(?:toevoegen|aanmaken|wijzigen|verwijderen|"
            r"add|create|update|delete|remove|hinzufügen|erstellen|ändern|löschen)\b",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _currency_amounts(text: str) -> set[str]:
        amounts = set()
        for match in re.finditer(
            r"(?:[€$]\s*([\d][\d.,]*)|([\d][\d.,]*)\s*(?:[€$]|\beuros?\b|\beur\b|\busd\b|\bdollars?\b))",
            text.casefold(),
        ):
            value = (match.group(1) or match.group(2)).rstrip(".,")
            if "," in value and "." in value:
                decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
            elif "," in value or "." in value:
                separator = "," if "," in value else "."
                decimal_separator = separator if len(value.rsplit(separator, 1)[-1]) <= 2 else ""
            else:
                decimal_separator = ""
            normalized = "".join(
                "." if character == decimal_separator else character
                for character in value if character.isdigit() or character == decimal_separator
            )
            try:
                amounts.add(str(Decimal(normalized).normalize()))
            except InvalidOperation:
                pass
        return amounts

    @staticmethod
    def _static_geometry_complete(
        text: str, evidence: tuple[dict[str, Any], ...], response_focus: str | None,
    ) -> bool:
        if response_focus != "calculation":
            return True
        geometries = [
            item["data"]["level_geometry"]
            for item in evidence
            if item.get("scope") == "read_linked_strategy"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and isinstance(item["data"].get("level_geometry"), dict)
            and item["data"]["level_geometry"].get("status") == "completed"
        ]
        if not geometries:
            return True
        values: set[Decimal] = set()
        for match in re.finditer(r"(?<![\w])\d+(?:[.,]\d+)*(?![\w])", text):
            token = match.group()
            pieces = re.split(r"[.,]", token)
            if len(pieces) > 1 and len(pieces[-1]) == 3:
                normalized = "".join(pieces)
            else:
                normalized = "".join(pieces[:-1]) + "." + pieces[-1] if len(pieces) > 1 else token
            try:
                values.add(Decimal(normalized))
            except InvalidOperation:
                continue
        for geometry in geometries:
            try:
                required = {Decimal(str(geometry["risk_per_unit"]))}
                required.update(Decimal(str(target["reward_to_risk"])) for target in geometry["targets"])
            except (KeyError, InvalidOperation, TypeError):
                return False
            if not required <= values:
                return False
        return True

    @staticmethod
    def _static_geometry_answer(
        evidence: tuple[dict[str, Any], ...], locale: str | None,
    ) -> str | None:
        for item in evidence:
            if item.get("scope") != "read_linked_strategy" or item.get("status") != "completed":
                continue
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            geometry = data.get("level_geometry")
            if not isinstance(geometry, dict) or geometry.get("status") != "completed":
                continue
            try:
                risk = Decimal(str(geometry["risk_per_unit"]))
                targets = [
                    (Decimal(str(target["price"])), Decimal(str(target["reward_per_unit"])),
                     Decimal(str(target["reward_to_risk"])))
                    for target in geometry["targets"]
                ]
            except (KeyError, InvalidOperation, TypeError):
                continue
            if not targets or risk <= 0:
                continue

            language = locale if locale in {"nl", "en", "de"} else "nl"

            def number(value: Decimal) -> str:
                normalized = format(value.normalize(), "f")
                integer, dot, fraction = normalized.partition(".")
                grouped = f"{int(integer):,}"
                if language != "en":
                    grouped = grouped.replace(",", ".")
                return grouped + (("," if language != "en" else ".") + fraction if dot else "")

            name = str(data.get("name") or "").strip()
            if language == "en":
                heading = f"From your saved strategy {name}, the entry-to-stop distance is {number(risk)} per unit."
                lines = [
                    f"At target {number(price)}, the potential gain is {number(reward)} per unit ({number(ratio)}:1)."
                    for price, reward, ratio in targets
                ]
                limit = "These are static calculations from saved levels, not a judgment about today's market or the likelihood of reaching a target."
            elif language == "de":
                heading = f"Aus deiner gespeicherten Strategie {name} ergibt sich ein Abstand von {number(risk)} je Einheit zwischen Einstieg und Stop-Loss."
                lines = [
                    f"Beim Ziel {number(price)} beträgt der mögliche Gewinn {number(reward)} je Einheit ({number(ratio)}:1)."
                    for price, reward, ratio in targets
                ]
                limit = "Das sind statische Berechnungen aus gespeicherten Kursniveaus, keine Beurteilung des heutigen Marktes oder der Zielwahrscheinlichkeit."
            else:
                heading = f"Uit je opgeslagen strategie {name} volgt een verschil van {number(risk)} per eenheid tussen entry en stop-loss."
                lines = [
                    f"Bij doel {number(price)} is de potentiële opbrengst {number(reward)} per eenheid ({number(ratio)}:1)."
                    for price, reward, ratio in targets
                ]
                limit = "Dit zijn statische berekeningen uit opgeslagen niveaus, geen oordeel over de huidige markt of de kans dat een doel wordt bereikt."
            return " ".join((heading, *lines, limit))
        return None

    @staticmethod
    def _question_matches_saved_geometry(message: str, evidence: tuple[dict[str, Any], ...]) -> bool:
        if re.search(r"\b(?:stel|hypothetisch|what if|hypothetical|angenommen)\b", message, re.I):
            return False
        mentioned = {
            Decimal(token.replace(".", "").replace(",", ""))
            for token in re.findall(r"(?<!\w)\d[\d.,]{2,}(?!\w)", message)
        }
        if not mentioned:
            return True
        for item in evidence:
            if item.get("scope") != "read_linked_strategy" or item.get("status") != "completed":
                continue
            data = item.get("data") or {}
            if not isinstance(data, dict):
                continue
            try:
                saved = {Decimal(str(data[key])) for key in ("entry", "stop_loss")}
                saved.update(Decimal(str(target)) for target in data.get("targets") or [])
            except (InvalidOperation, KeyError, TypeError):
                continue
            if mentioned <= saved:
                return True
        return False

    @classmethod
    def _amounts_supported(
        cls, *, answer: str, message: str, previous_answer: str,
        evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        claims = cls._currency_amounts(answer)
        if not claims:
            return True
        saved_setup_amount_unknown = any(
            item.get("scope") == "read_active_setup"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and item["data"].get("min_investment") is None
            for item in evidence
        )
        direction = re.compile(
            r"\b(?:verhog\w*|verhoog\w*|verlag\w*|verlaag\w*|stijg\w*|daal\w*|"
            r"increas\w*|decreas\w*|rais\w*|lower\w*|"
            r"erhöh\w*|senk\w*)\b", re.IGNORECASE,
        )
        if saved_setup_amount_unknown and not direction.search(message):
            for sentence in re.split(r"[.!?\n]+", answer):
                if (direction.search(sentence) and cls._currency_amounts(sentence)
                        and re.search(r"\b(?:dca|setup|invest\w*|inleg|betrag)\b", sentence, re.IGNORECASE)):
                    return False
        grounded = cls._currency_amounts(message) | cls._currency_amounts(previous_answer)

        def monetary_fields(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    field = str(key).casefold()
                    if isinstance(item, (int, float, Decimal)) and any(
                        token in field for token in (
                            "amount", "budget", "investment", "balance", "equity",
                            "pnl", "position_value", "invested_value",
                        )
                    ):
                        grounded.update(cls._currency_amounts(f"€{item}"))
                    monetary_fields(item)
            elif isinstance(value, list):
                for item in value:
                    monetary_fields(item)

        for item in evidence:
            if item.get("status") == "completed":
                monetary_fields(item.get("data"))
        return claims <= grounded

    @staticmethod
    def _percentage_claims_supported(
        *, answer: str, message: str, previous_answer: str,
        evidence: tuple[dict[str, Any], ...], response_focus: str | None,
    ) -> bool:
        pattern = re.compile(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:%|\b(?:procent|percent|prozent)\b)",
            re.IGNORECASE,
        )

        def percentages(value: str) -> set[Decimal]:
            return {Decimal(match.group(1).replace(",", ".")) for match in pattern.finditer(value)}

        claimed = percentages(answer)
        if not claimed:
            return True
        grounded = percentages(message) | percentages(previous_answer)

        def collect(value: Any, *, in_percent_map: bool = False) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    field = str(key).casefold()
                    if field == "level_geometry":
                        continue
                    is_percent = in_percent_map or any(
                        token in field for token in ("percent", "percentage", "_pct", "risk_per_trade")
                    )
                    if is_percent and not isinstance(item, (dict, list)):
                        try:
                            grounded.add(Decimal(str(item)))
                        except (InvalidOperation, TypeError):
                            pass
                    else:
                        collect(item, in_percent_map=is_percent)
            elif isinstance(value, list):
                for item in value:
                    collect(item, in_percent_map=in_percent_map)

        for item in evidence:
            if item.get("status") == "completed":
                collect(item.get("data"))
        price_distance_claims = {
            Decimal(match.group(1).replace(",", "."))
            for match in re.finditer(
                r"\b(?:risicoafstand|afstand|verschil|risk\s+distance|distance|difference|Abstand|Differenz)\b"
                r"[^.!?\n]{0,100}?\b(\d+(?:[.,]\d+)?)\s*"
                r"(?:%|\b(?:procent|percent|Prozent)\b)",
                answer, re.IGNORECASE,
            )
        }
        price_distance_claims.update(
            Decimal(match.group(1).replace(",", "."))
            for match in re.finditer(
                r"\b(\d+(?:[.,]\d+)?)\s*(?:%|\b(?:procent|percent|Prozent)\b)"
                r"[^.!?\n]{0,35}?\b(?:van (?:de )?entry|of (?:the )?entry|vom Einstieg)\b",
                answer, re.IGNORECASE,
            )
        )
        if price_distance_claims:
            for item in evidence:
                if item.get("scope") != "read_linked_strategy" or item.get("status") != "completed":
                    continue
                geometry = (item.get("data") or {}).get("level_geometry") if isinstance(item.get("data"), dict) else None
                if isinstance(geometry, dict) and geometry.get("status") == "completed":
                    try:
                        value = Decimal(str(geometry["entry_stop_distance_percent"]))
                    except (KeyError, InvalidOperation, TypeError):
                        continue
                    if value in price_distance_claims:
                        grounded.add(value)
        return claimed <= grounded

    @staticmethod
    def _static_risk_units_supported(answer: str, evidence: tuple[dict[str, Any], ...]) -> bool:
        risk_values = {
            Decimal(str(geometry["risk_per_unit"]))
            for item in evidence
            if item.get("scope") == "read_linked_strategy" and item.get("status") == "completed"
            for geometry in [(item.get("data") or {}).get("level_geometry")]
            if isinstance(geometry, dict) and geometry.get("status") == "completed"
            and geometry.get("risk_per_unit") is not None
        }
        if not risk_values:
            return True
        for match in re.finditer(
            r"\b(?:risicopercentage|risk\s+percentage|risikoprozentsatz)\b"
            r"[^.!?;\n]{0,45}\b(\d[\d.,]*)\b",
            answer, re.IGNORECASE,
        ):
            token = match.group(1)
            normalized = token.replace(".", "").replace(",", "") if re.search(r"[.,]\d{3}$", token) else token.replace(",", ".")
            try:
                if Decimal(normalized) in risk_values:
                    return False
            except InvalidOperation:
                continue
        return True

    @staticmethod
    def _asset_quantities_supported(
        *, answer: str, message: str, evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        assets = {
            str(item.get("asset") or "").upper()
            for item in evidence if item.get("status") == "completed"
        }
        for asset in assets:
            if not re.fullmatch(r"[A-Z]{2,8}", asset):
                continue
            quantity = re.compile(rf"\b\d+(?:[.,]\d+)?\s+{re.escape(asset)}\b", re.IGNORECASE)
            claims = {match.group().casefold() for match in quantity.finditer(answer)}
            if claims and not claims <= {match.group().casefold() for match in quantity.finditer(message)}:
                return False
        return True

    @staticmethod
    def _currency_units_supported(
        *, answer: str, message: str, previous_answer: str = "",
        evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        def units(text: str) -> set[str]:
            normalized = text.casefold()
            found = set()
            if re.search(r"(?:€\s*\d|\d\s*€|\d\s*(?:eur|euros?)\b)", normalized):
                found.add("EUR")
            if re.search(r"(?:\$\s*\d|\d\s*\$|\d\s*(?:usd|dollars?)\b)", normalized):
                found.add("USD")
            return found

        claimed = units(answer)
        allowed = units(message) | units(previous_answer)

        def collect_currency(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"currency", "base_currency", "quote_currency"}:
                        if str(item).upper() in {"EUR", "USD"}:
                            allowed.add(str(item).upper())
                    else:
                        collect_currency(item)
            elif isinstance(value, list):
                for item in value:
                    collect_currency(item)

        for item in evidence:
            if item.get("status") == "completed":
                collect_currency(item.get("data"))
        return claimed <= allowed

    async def _personal_advice_is_grounded(
        self, *, answer: str, evidence: list[dict[str, Any]], remaining: float | None,
        question: str | None = None, previous_answer: str | None = None,
        require_address_judgment: bool = True,
        require_actionable_next_decision: bool = False,
        answering_previous_question: bool = False,
        conditional_process: bool = False,
        locale: str | None = None,
        audit_diagnostics: dict[str, Any] | None = None,
    ) -> bool:
        if self.client is None:
            return False
        if remaining is not None and remaining <= 5:
            if audit_diagnostics is not None:
                audit_diagnostics["audit_unavailable"] = "insufficient_lifecycle_budget"
            logger.info("FINN personal advice audit skipped: lifecycle budget", extra={
                "stage": "responses_personal_advice_audit", "reason": "insufficient_lifecycle_budget",
                "remaining_seconds": round(remaining, 2),
            })
            return False
        timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    temperature=0,
                    instructions=(
                        "Audit a trading-coach answer against ONLY the typed evidence. Distinguish "
                        "stored user choices from evaluated market/risk evidence. A saved profile, "
                        "setup, strategy, entry, stop-loss or target proves its stored value, NOT "
                        "personal suitability, profitability, historical market conditions, a "
                        "need to change levels, or that changes will achieve investment goals. "
                        "The user's description of a plan rule is conversation input, not "
                        "proof that this rule exists in the saved setup or strategy. Mark "
                        "unsupported_personal_advice=true if the answer encourages bypassing "
                        "a precaution the user explicitly stated without verified current "
                        "evidence or a user-authorized change to that rule. A hypothetical "
                        "possibility that a fast market could reward acting earlier is not "
                        "evidence that this trader should override their rule. "
                        "user_claim_as_saved=true if the answer attributes such a rule, "
                        "trigger, amount or condition to a persisted object when the typed "
                        "read evidence does not contain it. The answer may instead say "
                        "'you describe a rule' and discuss its conditional consequence. "
                        "Use persisted_entity_evidence as a strict existence boundary. "
                        "If linked_strategy_completed is false, any claim that the user "
                        "already has, follows, or should keep following one or more saved "
                        "strategies is an unsupported entity claim, even when phrased as "
                        "general coaching. A saved setup is not a saved strategy. Do not "
                        "infer a strategy from conversation history or the user's label 'plan'. "
                        "General education, cautious questions, truthful descriptions of saved "
                        "settings, and invitations to CHECK suitability by obtaining current "
                        "market or owner-scoped risk evidence are allowed. 'Check whether these "
                        "saved levels suit your risk profile' does NOT claim they suit it. "
                        "A sentence that accurately restates the user's proposed change, such as "
                        "'you are considering 100 euros per week', is not advice and does not claim "
                        "that the amount is saved or suitable. A sentence that explicitly says "
                        "suitability cannot yet be determined without a risk assessment is a safe "
                        "limitation, not an unsupported suitability claim. Do not mark either as "
                        "unsupported_personal_advice. But a preliminary positive claim such as "
                        "'100 euros per week fits well with your conservative approach' IS "
                        "unsupported personal advice when no owner-scoped risk assessment exists, "
                        "even if the next sentence says that a final judgment is still missing. "
                        "Completed level_geometry from a saved owner-scoped strategy grounds "
                        "static risk per unit and reward-to-risk ratios. Reporting those "
                        "numbers or noting that saved levels make the calculation possible "
                        "does not claim suitability. Calling a ratio attractive, favorable "
                        "or convincing does. A requested plan review can name a verified "
                        "structural fact, an evidenced limitation, and a concrete check. "
                        "A requested priority list may contain the requested number of "
                        "distinct preparatory checks grounded in saved facts; do not require "
                        "reducing it to one choice or a generic data warning. "
                        "Set requested_structure_satisfied=false if the question asks for a "
                        "specific response structure that the answer omits: for example a "
                        "strength, restraint and next check in a review, or three separately "
                        "identifiable priorities plus what to avoid. Merely saying 'three "
                        "actions' without listing three is insufficient. For a calculation, "
                        "when completed level_geometry is in evidence, require its absolute "
                        "risk_per_unit AND the reward_to_risk of each target, plus the "
                        "inference limit; ratios alone omit the risk amount. Otherwise "
                        "set requested_structure_satisfied=true. "
                        "Set invented_rule_detail=true if an unspecified user-stated "
                        "wait or confirmation rule becomes a specific indicator, price-action "
                        "pattern, threshold or trigger absent from both the user's words and "
                        "typed evidence, or if the answer claims that such a detail improves "
                        "the chance of a successful trade. Otherwise set it false. "
                        "Check saved-object identity against the evidence scope: read_active_setup "
                        "is a setup, not a strategy. Calling that setup a 'plan' is acceptable when "
                        "the user calls it a plan; calling it a saved strategy is not. "
                        "An unavailable read_linked_strategy does not "
                        "prove that any linked strategy exists. Saying that the linked strategy "
                        "is missing or asking whether the user wants to create one is allowed; "
                        "neither claims a saved strategy exists. Mark unsupported_entity_claim=true "
                        "only when the answer calls a saved setup a saved strategy or invents a linked object. "
                        "When true, copy the shortest exact affirmative entity claim from the answer "
                        "into unsupported_entity_quote. Otherwise set that quote to an empty string. "
                        "For a review of a saved plan, treat typed unavailable plan components as "
                        "evidence limits, not as absent audit input. If a setup exists but its linked "
                        "strategy is unavailable, a next step that only waits for market data or "
                        "continues following the plan does not address the missing plan structure. "
                        "Mark actionable_next_decision=false unless the answer identifies a concrete "
                        "user-controlled way to clarify or complete that missing component, without "
                        "claiming a strategy must exist for every DCA setup. "
                        "Mark proposed_as_saved=true when a value mentioned only in the user's "
                        "hypothetical proposal is described as the current persisted setting. "
                        "A proposal of 100 euros per week is not a saved amount when the saved "
                        "setup's min_investment is null. Otherwise set proposed_as_saved=false. "
                        "Set proposed_change_omitted=true when the current question asks whether "
                        "a specific proposed change is suitable but the answer discusses only the "
                        "saved setup or missing evidence and never identifies that proposed change "
                        "as hypothetical. The exact wording need not be repeated, but the relevant "
                        "amount, cadence or other changed value must remain distinguishable from "
                        "stored facts. For questions without a proposed change set it false. "
                        "When the latest user message answers FINN's preceding question, "
                        "the new detail is not a new proposed action: do not require an older "
                        "hypothetical change to be repeated. "
                        "Mark unsupported_personal_advice true if "
                        "the answer implies any unevidenced personal recommendation, causal "
                        "market history, or suitability claim. In particular, if a saved entry "
                        "is 100, a stop is 90 and a target is 120, 'the saved settings are 100, "
                        "90 and 120' is factual. 'Begin investing at 100', 'set your stop at "
                        "90', 'take profit at 120', or 'this structure offers strategic "
                        "advantage' are recommendations, NOT established facts. Mark those "
                        "unsupported unless an explicit current owner-scoped evaluation supports "
                        "them. Do not assume missing evidence. If a question is supplied, also "
                        "judge whether the answer directly addresses it using verified saved "
                        "settings, or honestly says that suitability is not yet established and "
                        "offers the missing evaluation. Such a limited answer IS complete for a "
                        "request for a logical personal plan when no current evaluation exists. "
                        "A generic refusal or a repeated setup-choice question is not complete. "
                        "Do not ask the user to choose or supply a value that is already explicit "
                        "in the current question or previous verified answer. For example, when "
                        "the user already proposed an amount and frequency, asking them to pick "
                        "an amount again is not a useful next step; mark addresses_request=false. "
                        "When previous_verified_answer is supplied, a follow-up must answer from "
                        "the verified answer text supplied there rather than introduce a new "
                        "indicator, market assertion or "
                        "recommendation found only in older tool evidence. If it does, mark "
                        "unsupported_personal_advice=true. "
                        "When an unavailable source has no verified cause, treating a provider "
                        "outage, delay or technical fault as its cause is unsupported personal "
                        "advice: set unsupported_personal_advice=true. "
                        "If typed evaluation_boundary has assessment_status=insufficient_evidence, "
                        "distinguish describing the user's proposed change from inviting them to "
                        "confirm or implement it now. The latter is premature when they asked "
                        "whether it is suitable: set premature_action_invitation=true. A choice "
                        "to leave the saved setup unchanged is not an action invitation. Otherwise "
                        "set premature_action_invitation=false. "
                        "A question that asks whether the user wants to change a saved setup so it "
                        "better fits their goals is also a premature action invitation when neither "
                        "the user's horizon nor a suitability evaluation is established. Ask for "
                        "the missing horizon instead. "
                        "If the user asks which choice or preparatory step to make next, merely "
                        "repeating why an evaluation is unavailable does not address the request. "
                        "When the user asks whether to bypass a rule they just described, an "
                        "inventory of saved fields and a statement that market data is missing "
                        "does not answer the question: set addresses_request=false. A grounded "
                        "answer explains the conditional process choice without claiming that "
                        "the described rule is saved or that its market trigger is satisfied. "
                        "The answer must identify concrete, evidence-supported next steps "
                        "the user can actually make, without pretending to know which trade is "
                        "personally suitable. 'Decide about missing market data' is not a user "
                        "decision; mark addresses_request=false for that kind of answer. "
                        "Set question_requests_choice=true when the user asks whether to do "
                        "something, whether to bypass their stated rule, or what to do next. "
                        "For such a question, 'it is your choice', an inventory of saved data, "
                        "or only saying that current data is missing is NOT a concrete process "
                        "decision: set actionable_next_decision=false. A safe decision can be "
                        "to follow a user-stated wait rule until its condition is checked, "
                        "without claiming that rule is saved or that the condition is met. "
                        "Set actionable_next_decision=true only when a next-decision answer "
                        "names concrete choices under the user's control that follow from "
                        "the verified previous answer. Choosing which unavailable market data "
                        "or indicators to investigate is not such a choice. If the typed evaluation "
                        "says those sources are unavailable, suggesting that the user request a "
                        "market analysis or technical snapshot is likewise not a usable first "
                        "decision; set actionable_next_decision=false. Choosing to leave "
                        "the saved setup unchanged until a valid assessment is possible is. "
                        "For other questions set actionable_next_decision=true. "
                        "For a typed conditional_process answer, judge whether the answer "
                        "responds to the user's process choice under their stated rule. "
                        "Saying not to bypass a user-stated wait rule merely due to FOMO is "
                        "a concrete safe process decision, not a claim that the rule is saved "
                        "or that a trade is suitable. A conditional reminder to check the "
                        "rule's conditions before acting is actionable. Still reject any "
                        "claim that today's entry condition is satisfied or any new trade "
                        "recommendation without evidence. "
                        "When no question is supplied, set addresses_request=true. The answer "
                        "must use the supplied preferred_locale when present, unless the question "
                        "explicitly requests another language. Mark language_mismatch=true if any "
                        "user-facing sentence switches to a different language; object names are exempt. "
                        "Mark unnatural_language=true only for conspicuously broken grammar, "
                        "invented compound words, duplicated fragments, or backend-style prose "
                        "that a user would not expect from a clear personal coach. Do not flag "
                        "ordinary variation or a minor typo."
                    ),
                    input=json.dumps(
                        {"answer": answer, "evidence": evidence, "question": question,
                         "persisted_entity_evidence": {
                             "active_setup_completed": any(
                                 item.get("scope") == "read_active_setup"
                                 and item.get("status") == "completed" for item in evidence
                             ),
                             "linked_strategy_completed": any(
                                 item.get("scope") == "read_linked_strategy"
                                 and item.get("status") == "completed" for item in evidence
                             ),
                         },
                         "preferred_locale": locale,
                         "conditional_process": conditional_process,
                         "answering_previous_question": answering_previous_question,
                         "previous_verified_answer": previous_answer},
                        ensure_ascii=False, default=str,
                    ),
                    text={"format": {
                        "type": "json_schema", "name": "finn_personal_advice_check", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "unsupported_personal_advice": {"type": "boolean"},
                                "unsupported_entity_claim": {"type": "boolean"},
                                "unsupported_entity_quote": {"type": "string"},
                                "user_claim_as_saved": {"type": "boolean"},
                                "proposed_as_saved": {"type": "boolean"},
                                "proposed_change_omitted": {"type": "boolean"},
                                "premature_action_invitation": {"type": "boolean"},
                                "language_mismatch": {"type": "boolean"},
                                "unnatural_language": {"type": "boolean"},
                                "addresses_request": {"type": "boolean"},
                                "question_requests_choice": {"type": "boolean"},
                                "actionable_next_decision": {"type": "boolean"},
                                "requested_structure_satisfied": {"type": "boolean"},
                                "invented_rule_detail": {"type": "boolean"},
                            },
                            "required": ["unsupported_personal_advice", "unsupported_entity_claim",
                                         "unsupported_entity_quote",
                                         "user_claim_as_saved",
                                         "proposed_as_saved", "proposed_change_omitted",
                                         "premature_action_invitation",
                                         "language_mismatch", "unnatural_language", "addresses_request",
                                         "question_requests_choice", "actionable_next_decision",
                                         "requested_structure_satisfied", "invented_rule_detail"],
                        },
                    }},
                    max_output_tokens=240,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            language_rejected = (
                parsed.get("language_mismatch") is True
                and not self._language_matches(answer, locale)
            )
            entity_quote = str(parsed.get("unsupported_entity_quote") or "").strip()
            entity_sentence = ""
            if entity_quote and entity_quote in answer:
                quote_start = answer.index(entity_quote)
                sentence_start = max(
                    answer.rfind(separator, 0, quote_start) for separator in ".!?\n"
                ) + 1
                sentence_end_candidates = [
                    position for separator in ".!?\n"
                    if (position := answer.find(separator, quote_start + len(entity_quote))) >= 0
                ]
                sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(answer)
                entity_sentence = answer[sentence_start:sentence_end]
            unsupported_entity_claim = (
                parsed.get("unsupported_entity_claim") is True
                and not (
                    entity_sentence
                    and bool(re.search(
                        r"\b(?:niet|geen|onbekend|onduidelijk|not|no|unknown|unclear|"
                        r"nicht|kein(?:e|en|er|es)?|unbekannt|unklar)\b",
                        entity_sentence, re.IGNORECASE,
                    ))
                )
            )
            parsed["unsupported_entity_claim"] = unsupported_entity_claim
            rejected_checks = [
                field for field in (
                    "unsupported_personal_advice", "unsupported_entity_claim",
                    "proposed_as_saved",
                    "premature_action_invitation",
                    "unnatural_language",
                ) if parsed.get(field) is not False
            ]
            if parsed.get("user_claim_as_saved", False) is not False:
                rejected_checks.append("user_claim_as_saved")
            if language_rejected:
                rejected_checks.append("language_mismatch")
            if require_address_judgment and question is not None and parsed.get("addresses_request") is not True:
                rejected_checks.append("does_not_address_request")
            decision_required = (
                require_actionable_next_decision
                or parsed.get("question_requests_choice") is True
            )
            if (not answering_previous_question and not require_actionable_next_decision
                    and parsed.get("proposed_change_omitted") is not False):
                rejected_checks.append("proposed_change_omitted")
            if decision_required and parsed.get("actionable_next_decision") is not True:
                rejected_checks.append("no_actionable_next_decision")
            if parsed.get("requested_structure_satisfied", True) is not True:
                rejected_checks.append("requested_structure_missing")
            if parsed.get("invented_rule_detail", False) is not False:
                rejected_checks.append("invented_rule_detail")
            if rejected_checks:
                logger.info("FINN personal advice audit rejected answer: checks=%s", rejected_checks,
                            extra={"stage": "responses_personal_advice_audit"})
            if audit_diagnostics is not None:
                audit_diagnostics["rejected_checks"] = rejected_checks
            return all(parsed.get(field) is False for field in (
                "unsupported_personal_advice", "unsupported_entity_claim",
                "proposed_as_saved",
                "premature_action_invitation",
                "unnatural_language",
            )) and parsed.get("user_claim_as_saved", False) is False and not language_rejected and (
                not require_address_judgment or question is None or parsed.get("addresses_request") is True
            ) and (
                not decision_required or parsed.get("actionable_next_decision") is True
            ) and (
                answering_previous_question or require_actionable_next_decision
                or parsed.get("proposed_change_omitted") is False
            ) and (
                parsed.get("requested_structure_satisfied", True) is True
            ) and (
                parsed.get("invented_rule_detail", False) is False
            )
        except Exception as exc:
            if audit_diagnostics is not None:
                audit_diagnostics["audit_unavailable"] = type(exc).__name__
            logger.info("FINN personal advice audit unavailable: %s", type(exc).__name__, extra={
                "stage": "responses_personal_advice_audit", "reason": "audit_unavailable",
            })
            return False

    async def _technical_limitation_is_grounded(
        self, *, answer: str, remaining: float | None,
    ) -> bool:
        if self.client is None or (remaining is not None and remaining <= 5):
            return False
        timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    instructions=(
                        "Audit this answer to a question about current technical indicators. "
                        "The current technical snapshot is unavailable. Do not infer a temporary "
                        "outage, provider failure, delay or other cause. Do not claim a current RSI, "
                        "moving-average reading, or combined market signal. General educational "
                        "statements must also be materially correct: RSI above 70 is commonly "
                        "called overbought and below 30 oversold, not the reverse. Flag any "
                        "unsupported cause, invented reading, or material technical error."
                    ),
                    input=answer,
                    text={"format": {
                        "type": "json_schema", "name": "finn_technical_limitation_check", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"grounded": {"type": "boolean"}},
                            "required": ["grounded"],
                        },
                    }},
                    max_output_tokens=40,
                ),
                timeout=timeout,
            )
            return json.loads(str(getattr(response, "output_text", "") or "")).get("grounded") is True
        except Exception:
            return False

    async def _catalog_answer_is_focused(
        self, *, question: str, answer: str, options: list[dict[str, str]], remaining: float | None,
    ) -> tuple[bool, str]:
        if self.client is None or (remaining is not None and remaining <= 5):
            return False, ""
        timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o-mini", store=False, tool_choice="none",
                    instructions=(
                        "Decide whether the user asks for exactly one indicator candidate, "
                        "and check whether the proposed answer respects the NUMBER and KIND of "
                        "indicator choices requested. If the user asks for one missing "
                        "indicator and why, an answer naming none or listing several catalog "
                        "entries is not focused. "
                        "An answer that falsely says the user wants or is considering "
                        "adding an indicator is also unfocused when the user only asked "
                        "which indicator is missing. Do not refuse a configuration-gap "
                        "answer merely because live market snapshots are unavailable. "
                        "A broad request for several options may legitimately receive a list. "
                        "If the answer is unfocused, select exactly one of the supplied options "
                        "and mention it by its EXACT supplied display_name in "
                        "a brief replacement in the "
                        "question's language explaining its "
                        "general purpose. Do not assert a current reading, correlation or trade "
                        "conclusion. If one candidate is requested but the answer names none, "
                        "focused must be false and replacement must name one option. For a "
                        "focused answer, leave selected_option and replacement empty."
                    ),
                    input=json.dumps({
                        "question": question, "answer": answer,
                        "supported_catalog_options": options,
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_catalog_answer_focus", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "one_candidate_requested": {"type": "boolean"},
                                "focused": {"type": "boolean"},
                                "selected_option": {"type": "string"},
                                "replacement": {"type": "string"},
                            },
                            "required": ["one_candidate_requested", "focused", "selected_option", "replacement"],
                        },
                    }},
                    max_output_tokens=180,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            mentioned_options = [
                option for option in options
                if str(option.get("display_name") or "").casefold() in answer.casefold()
                or re.search(
                    rf"\b{re.escape(str(option.get('name') or ''))}\b",
                    answer, re.IGNORECASE,
                )
            ]
            one_candidate_missing = (
                parsed.get("one_candidate_requested") is True
                and len(mentioned_options) != 1
            )
            if parsed.get("focused") is True and not one_candidate_missing:
                return True, ""
            selected = str(parsed.get("selected_option") or "")
            replacement = str(parsed.get("replacement") or "").strip()
            selected_option = next((
                option for option in options
                if selected.casefold() in {
                    str(option.get("name") or "").casefold(),
                    str(option.get("display_name") or "").casefold(),
                }
            ), None)
            if parsed.get("one_candidate_requested") is True and (
                selected_option is None or not replacement
            ):
                remaining = remaining_lifecycle_seconds()
                retry_timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
                if retry_timeout <= 0:
                    return False, ""
                suggestion = await asyncio.wait_for(
                    client.responses.create(
                        model="gpt-4o-mini", store=False, tool_choice="none",
                        instructions=(
                            "The user requests one missing macro-indicator and a brief reason. "
                            "Choose exactly one supplied existing catalog option. Write one "
                            "sentence in the question's language naming its exact display_name "
                            "and general purpose. Do not claim a current reading, personal "
                            "suitability, expected return, or that the user already intends "
                            "to add it. This is a read answer, not a proposal."
                        ),
                        input=json.dumps({"question": question, "options": options}, ensure_ascii=False),
                        text={"format": {
                            "type": "json_schema", "name": "finn_catalog_single_choice",
                            "strict": True,
                            "schema": {
                                "type": "object", "additionalProperties": False,
                                "properties": {
                                    "selected_option": {
                                        "type": "string",
                                        "enum": [str(option["name"]) for option in options],
                                    },
                                    "answer": {"type": "string"},
                                },
                                "required": ["selected_option", "answer"],
                            },
                        }},
                        max_output_tokens=150,
                    ),
                    timeout=retry_timeout,
                )
                choice = json.loads(str(getattr(suggestion, "output_text", "") or ""))
                selected_option = next((
                    option for option in options
                    if option["name"] == choice.get("selected_option")
                ), None)
                replacement = str(choice.get("answer") or "").strip()

            def mentioned(option: dict[str, str]) -> bool:
                normalized_answer = re.sub(r"[^a-z0-9]", "", replacement.casefold())
                display = str(option.get("display_name") or "")
                labels = (
                    str(option.get("name") or ""), display,
                    display.split("(", 1)[0].strip(),
                )
                return any(
                    len(normalized_label) >= 3 and normalized_label in normalized_answer
                    for label in labels
                    if (normalized_label := re.sub(r"[^a-z0-9]", "", label.casefold()))
                )

            logger.info(
                "FINN catalog selection checked: known=%s mentioned=%s competing=%s",
                selected_option is not None,
                mentioned(selected_option) if selected_option else False,
                any(option is not selected_option and mentioned(option) for option in options),
            )
            if selected_option is None:
                return False, ""
            if not mentioned(selected_option):
                replacement = f"{selected_option.get('display_name') or selected_option.get('name')}: {replacement}"
            if any(
                option is not selected_option and mentioned(option)
                for option in options
            ):
                return False, ""
            return False, replacement
        except Exception:
            return False, ""

    async def verify(
        self, *, message: str, result: FinnResponsesResult,
        previous_response: dict[str, Any] | None = None,
        recent_action_result: dict[str, Any] | None = None,
        locale: str | None = None,
    ) -> FinnResponsesVerifiedAnswer:
        evidence = tuple(
            item
            for call in result.tool_trace
            for item in (call.get("result", {}).get("results") or [])
            if isinstance(item, dict)
        )
        if result.answer_kind in {"saved_inventory_unavailable", "cross_asset_inventory_unavailable"}:
            language = locale if locale in {"nl", "en", "de"} else "nl"
            if result.answer_kind == "cross_asset_inventory_unavailable":
                arguments = next((
                    call.get("arguments") for call in result.tool_trace
                    if isinstance(call.get("arguments"), dict)
                ), {})
                source = str(arguments.get("source_asset") or "").upper()
                target = str(arguments.get("target_asset") or "").upper()
                answer = {
                    "nl": f"Nee, een regel voor {source} geldt niet automatisch voor {target}. Ik kan je opgeslagen setups op dit moment niet betrouwbaar uitlezen, dus ik kan geen {target}-plan bevestigen.",
                    "en": f"No, a rule for {source} does not automatically apply to {target}. I cannot reliably read your saved setups right now, so I cannot confirm a {target} plan.",
                    "de": f"Nein, eine Regel für {source} gilt nicht automatisch für {target}. Ich kann Deine gespeicherten Setups gerade nicht zuverlässig lesen und deshalb keinen {target}-Plan bestätigen.",
                }[language]
            else:
                answer = {
                    "nl": "Ik kan je opgeslagen setups op dit moment niet betrouwbaar uitlezen. Probeer deze vraag later opnieuw; ik wil geen namen of regels gokken.",
                    "en": "I cannot reliably read your saved setups right now. Please try again later; I do not want to guess names or rules.",
                    "de": "Ich kann Deine gespeicherten Setups gerade nicht zuverlässig lesen. Bitte versuche es später erneut; ich möchte keine Namen oder Regeln raten.",
                }[language]
            return FinnResponsesVerifiedAnswer(
                "completed", answer, result.answer_kind, evidence,
            )
        if result.answer_kind == "cross_asset_rule_scope":
            source_target = next((
                call.get("arguments") for call in result.tool_trace
                if call.get("name") == "get_saved_setup_inventory"
                and isinstance(call.get("arguments"), dict)
            ), {})
            source = str(source_target.get("source_asset") or "").upper()
            target = str(source_target.get("target_asset") or "").upper()
            setup_read = next((
                item for item in evidence
                if item.get("scope") == "read_saved_setup_inventory"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and isinstance(item["data"].get("setups"), list)
            ), None)
            if source and target and setup_read is not None:
                target_names = [
                    str(row["name"]) for row in setup_read["data"]["setups"]
                    if isinstance(row, dict) and row.get("name")
                    and str(row.get("symbol") or "").upper() == target
                ]
                language = locale if locale in {"nl", "en", "de"} else "nl"
                answer = {
                    "nl": f"Nee, een regel voor {source} geldt niet automatisch voor {target}.",
                    "en": f"No, a rule for {source} does not automatically apply to {target}.",
                    "de": f"Nein, eine Regel für {source} gilt nicht automatisch für {target}.",
                }[language]
                if target_names:
                    names = ", ".join(f"‘{name}’" for name in target_names)
                    answer += {
                        "nl": f" Ik zie voor {target} deze opgeslagen setups: {names}. Hun eigen voorwaarden moet je afzonderlijk bekijken.",
                        "en": f" I can see these saved {target} setups: {names}. Check their own conditions separately.",
                        "de": f" Ich sehe diese gespeicherten {target}-Setups: {names}. Prüfe ihre Bedingungen separat.",
                    }[language]
                else:
                    answer += ({
                        "nl": f" In het gelezen setupoverzicht zie ik geen {target}-plan.",
                        "en": f" I do not see a {target} plan in the setup overview I read.",
                        "de": f" In der gelesenen Setup-Übersicht sehe ich keinen {target}-Plan.",
                    } if setup_read["data"].get("complete", True) else {
                        "nl": f" Het setupoverzicht is afgekapt; ik kan niet vaststellen of er een {target}-plan is.",
                        "en": f" The setup inventory is truncated; I cannot determine whether a {target} plan exists.",
                        "de": f" Die Setup-Übersicht ist gekürzt; ob ein {target}-Plan besteht, bleibt offen.",
                    })[language]
                if re.search(r"\b(?:fomo|impulsief|impulsive|impulsiv)\b", message, re.I):
                    answer += {
                        "nl": " Als FOMO de aanleiding is, behandel die eerst als signaal om je plan te controleren, niet als reden om de BTC-regel over te nemen.",
                        "en": " If FOMO is driving the question, use it as a cue to check your plan before applying the BTC rule elsewhere.",
                        "de": " Wenn FOMO der Anlass ist, prüfe zuerst Deinen Plan, bevor Du die BTC-Regel anderswo anwendest.",
                    }[language]
                return FinnResponsesVerifiedAnswer(
                    "completed", answer, "cross_asset_rule_scope", evidence,
                )
        if result.answer_kind == "listed_setup_reference_out_of_range":
            return FinnResponsesVerifiedAnswer(
                "completed", {
                    "nl": "Dat nummer staat niet in de setup-lijst die ik net noemde. Welk van de genoemde namen bedoel je?",
                    "en": "That position was not in the setup list I just gave. Which listed name do you mean?",
                    "de": "Diese Position stand nicht in der eben genannten Setup-Liste. Welchen der genannten Namen meinst du?",
                }[locale if locale in {"nl", "en", "de"} else "nl"],
                "listed_setup_reference_out_of_range", evidence,
            )
        if result.answer_kind == "listed_setup_reference":
            reference_call = next((
                call for call in result.tool_trace
                if call.get("name") == "get_saved_setup_inventory"
            ), {})
            ordinal = (reference_call.get("arguments") or {}).get("listed_ordinal")
            inventory = next((
                item.get("data") for item in evidence
                if item.get("scope") == "read_saved_setup_inventory"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
            ), {})
            rows = [
                row for row in inventory.get("setups") or []
                if isinstance(row, dict) and row.get("name")
            ]
            language = locale if locale in {"nl", "en", "de"} else "nl"
            if not rows:
                return FinnResponsesVerifiedAnswer(
                    "completed", {
                        "nl": "Die setup uit mijn vorige lijst kan ik nu niet meer terugvinden. Vraag om een nieuw overzicht, dan controleer ik de actuele lijst.",
                        "en": "I cannot find that setup from my previous list now. Ask for a fresh inventory and I will check the current list.",
                        "de": "Dieses Setup aus meiner vorherigen Liste kann ich jetzt nicht mehr finden. Frage nach einer neuen Übersicht, dann prüfe ich die aktuelle Liste.",
                    }[language], "listed_setup_reference", evidence,
                )
            row = rows[0]
            name = str(row["name"])
            position = str(ordinal) if isinstance(ordinal, int) else "?"
            answer = {
                "nl": f"Nummer {position} uit mijn lijst is ‘{name}’.",
                "en": f"Number {position} on my list is ‘{name}’.",
                "de": f"Nummer {position} auf meiner Liste ist ‘{name}’.",
            }[language]
            if re.search(r"\b(?:meer|details?|informatie|vertel|about|explain|mehr|erzähl)\b", message, re.I):
                asset = str(row.get("symbol") or "").upper()
                timeframe = str(row.get("timeframe") or "").upper()
                setup_type = str(row.get("setup_type") or "").lower()
                details = {
                    "nl": f"Het is een {asset + '-' if asset else ''}{setup_type + '-' if setup_type else ''}setup",
                    "en": f"It is a {asset + ' ' if asset else ''}{setup_type + ' ' if setup_type else ''}setup",
                    "de": f"Es ist ein {asset + '-' if asset else ''}{setup_type + '-' if setup_type else ''}Setup",
                }[language]
                if timeframe:
                    details += {
                        "nl": f" op timeframe {timeframe}",
                        "en": f" on the {timeframe} timeframe",
                        "de": f" im Zeitrahmen {timeframe}",
                    }[language]
                answer += " " + details + "."
            if re.search(r"\b(?:entry\w*|instap\w*|bevestig\w*|confirmation|trigger\w*)\b", message, re.I):
                answer += {
                    "nl": " Deze setupgegevens bevatten geen apart veld met een instapbevestiging; een gekoppelde strategie is hiermee niet gecontroleerd.",
                    "en": " This setup record has no separate entry-confirmation field; a linked strategy has not been checked here.",
                    "de": " Dieser Setup-Datensatz hat kein eigenes Feld für eine Einstiegsbestätigung; eine verknüpfte Strategie wurde hier nicht geprüft.",
                }[language]
            return FinnResponsesVerifiedAnswer(
                "completed", answer, "listed_setup_reference", evidence,
            )
        if result.answer_kind == "saved_confirmation_inventory":
            inventory = next((
                item.get("data") for item in evidence
                if item.get("scope") == "read_saved_setup_inventory"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and isinstance(item["data"].get("setups"), list)
            ), None)
            if inventory is not None:
                rows = [row for row in inventory["setups"] if isinstance(row, dict) and row.get("name")]
                names = ", ".join(f"‘{row['name']}’" for row in rows)
                language = locale if locale in {"nl", "en", "de"} else "nl"
                if not inventory.get("complete", True):
                    return FinnResponsesVerifiedAnswer(
                        "completed", {
                            "nl": f"Ik zie ten minste {len(rows)} setups in het gelezen deel: {names}. Het overzicht is afgekapt, dus ik kan niet bepalen of een van alle opgeslagen setups een instapvoorwaarde bevat.",
                            "en": f"I can see at least {len(rows)} setups in the retrieved portion: {names}. The inventory is truncated, so I cannot assess every saved setup's entry condition.",
                            "de": f"Ich sehe mindestens {len(rows)} Setups im gelesenen Teil: {names}. Die Übersicht ist gekürzt; ich kann daher nicht alle Einstiegsbedingungen prüfen.",
                        }[language], "saved_confirmation_inventory", evidence,
                    )
                answer = {
                    "nl": (
                        f"Ik zie {len(rows)} opgeslagen setups: {names}. "
                        "In deze setupgegevens staat bij geen daarvan een apart veld met een "
                        "bevestigings- of instapregel. Ik kan dus geen van deze setups met zo'n "
                        "opgeslagen regel aanwijzen; eventuele gekoppelde strategieën zijn "
                        "hiermee nog niet gecontroleerd."
                    ),
                    "en": (
                        f"I can see {len(rows)} saved setups: {names}. "
                        "None of these setup records has a separate confirmation or entry-rule field. "
                        "I cannot identify one with a saved rule from this inventory; linked "
                        "strategies have not been checked here."
                    ),
                    "de": (
                        f"Ich sehe {len(rows)} gespeicherte Setups: {names}. "
                        "Keiner dieser Setup-Datensätze enthält ein eigenes Feld für eine "
                        "Bestätigungs- oder Einstiegsregel. Eine solche gespeicherte Regel kann "
                        "ich hier nicht zuordnen; verknüpfte Strategien wurden nicht geprüft."
                    ),
                }[language]
                return FinnResponsesVerifiedAnswer(
                    "completed", answer, "saved_confirmation_inventory", evidence,
                )
        if result.answer_kind == "saved_confirmation_collection":
            answer = self._saved_confirmation_answer(message, evidence, locale)
            if answer:
                return FinnResponsesVerifiedAnswer(
                    "completed", answer, "saved_confirmation_readback", evidence,
                )
        if result.answer_kind == "saved_setup_collection":
            setup_read = next((
                item for item in evidence
                if item.get("scope") == "read_saved_setup_inventory"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and isinstance(item["data"].get("setups"), list)
            ), None)
            if setup_read is not None:
                rows = [
                    row for row in setup_read["data"]["setups"]
                    if isinstance(row, dict) and row.get("name")
                ]
                if rows:
                    assets = {str(row.get("symbol") or "").upper() for row in rows}
                    labels = ", ".join(
                        f"‘{row['name']}’ ({str(row.get('symbol') or '').upper()})"
                        if len(assets) > 1 else f"‘{row['name']}’"
                        for row in rows
                    )
                    language = locale if locale in {"nl", "en", "de"} else "nl"
                    if not setup_read["data"].get("complete", True):
                        return FinnResponsesVerifiedAnswer(
                            "completed", {
                                "nl": f"Ik zie ten minste {len(rows)} opgeslagen setups in het gelezen deel: {labels}. Het overzicht is afgekapt.",
                                "en": f"I can see at least {len(rows)} saved setups in the retrieved portion: {labels}. The inventory is truncated.",
                                "de": f"Ich sehe mindestens {len(rows)} gespeicherte Setups im gelesenen Teil: {labels}. Die Übersicht ist gekürzt.",
                            }[language], "saved_setup_collection", evidence,
                        )
                    answer = {
                        "nl": f"Ik zie {len(rows)} opgeslagen setups: {labels}.",
                        "en": f"I can see {len(rows)} saved setups: {labels}.",
                        "de": f"Ich sehe {len(rows)} gespeicherte Setups: {labels}.",
                    }[language]
                    return FinnResponsesVerifiedAnswer(
                        "completed", answer, "saved_setup_collection", evidence,
                    )
                language = locale if locale in {"nl", "en", "de"} else "nl"
                return FinnResponsesVerifiedAnswer(
                    "completed", {
                        "nl": "Ik zie geen opgeslagen setups in dit overzicht.",
                        "en": "I see no saved setups in this inventory.",
                        "de": "Ich sehe in dieser Übersicht keine gespeicherten Setups.",
                    }[language], "saved_setup_collection", evidence,
                )
        if (
            not previous_response and not recent_action_result and not result.tool_trace
            and result.answer_kind != "provider_unavailable"
            and FinnV2RequestPreprocessorService().preprocess(message=message).ambiguous_reference
        ):
            question = {
                "nl": "Waar verwijs je naar? Geef me de vraag of conclusie die je bedoelt, dan denk ik met je mee.",
                "en": "What are you referring to? Tell me which question or conclusion you mean, and I'll help you from there.",
                "de": "Worauf beziehst du dich? Nenne mir die Frage oder Schlussfolgerung, die du meinst, dann helfe ich dir weiter.",
            }[locale if locale in {"nl", "en", "de"} else "nl"]
            return FinnResponsesVerifiedAnswer(
                "clarification_required", question, "previous_response_unavailable", evidence,
                clarification={"question": question, "reason": "previous_response_unavailable"},
            )
        if result.answer_kind == "provider_unavailable":
            if result.model_led_coach and _read_only_stop_loss_coaching(message):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._stop_loss_coach_fallback(locale),
                    "safe_stop_loss_coaching", evidence,
                )
            if result.model_led_coach and _hypothetical_trade_reflection(message):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._hypothetical_reflection_fallback(locale),
                    "safe_hypothetical_reflection", evidence,
                )
            return FinnResponsesVerifiedAnswer(
                "unavailable", self._fallback_copy(
                    "responses_provider_timeout", message=message, locale=locale,
                ), "responses_provider_timeout", evidence,
            )
        calculation_question = bool(re.search(
            r"\b(?:verhouding|bereken|berekening|risk.reward|reward.to.risk|calculate|ratio|"
            r"verhältnis|berechne)\b", message, re.I,
        )) and not bool(re.search(
            r"\b(?:moet\s+ik|should\s+i|soll\s+ich)\b", message, re.I,
        ))
        static_answer = (
            self._static_geometry_answer(evidence, locale)
            if result.response_focus == "calculation" or (
                result.model_led_coach and calculation_question
                and self._question_matches_saved_geometry(message, evidence)
            )
            else None
        )
        if any(call.get("status") == "error" for call in result.tool_trace):
            return FinnResponsesVerifiedAnswer(
                "unavailable", self._fallback_copy("source_unavailable", message=message, locale=locale),
                "responses_tool_execution_failed", evidence,
            )
        if static_answer and not any(
            (call.get("result") or {}).get("proposal_id") for call in result.tool_trace
        ):
            return FinnResponsesVerifiedAnswer(
                "completed", static_answer, "static_level_geometry", evidence,
            )
        clarification_calls = [
            call for call in result.tool_trace
            if call.get("name") == "ask_for_clarification" and call.get("status") == "needs_input"
        ]
        if clarification_calls:
            clarification = dict(clarification_calls[-1].get("result") or {})
            return FinnResponsesVerifiedAnswer(
                "clarification_required", str(clarification["question"]),
                str(clarification["reason"]), evidence,
                clarification={
                    "question": str(clarification["question"]),
                    "reason": str(clarification["reason"]),
                },
            )
        if result.model_led_coach:
            saved_confirmation = self._saved_confirmation_answer(message, evidence, locale)
            if saved_confirmation:
                return FinnResponsesVerifiedAnswer(
                    "completed", saved_confirmation, "saved_confirmation_readback", evidence,
                )
            if (
                _hypothetical_trade_reflection(message)
                and not any(item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                            and item.get("status") == "completed" for item in evidence)
                and re.search(
                    r"\b(?:jouw|je|your|deine?)\s+(?:opgeslagen\s+|saved\s+)?"
                    r"(?:instapregel|entryregel|entry\s+rule|bevestigingsregel)\b"
                    r"|\b(?:instapregel|entryregel|entry\s+rule)\b.{0,35}"
                    r"\b(?:uit|in|from)\s+(?:je|jouw|your|het|the)\s+plan\b",
                    result.text, re.I,
                )
                and not re.search(
                    r"\b(?:geen|no|not|niet|keine?)\b.{0,35}"
                    r"\b(?:instapregel|entryregel|entry\s+rule|bevestigingsregel)\b",
                    result.text, re.I,
                )
            ):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._hypothetical_reflection_fallback(locale),
                    "safe_hypothetical_reflection", evidence,
                )
            if _read_only_stop_loss_coaching(message) and re.search(
                r"\b(?:hoeft.{0,30}(?:geen|niet.{0,20})(?:stop)?order|"
                r"vervang.{0,40}(?:mentale|zelfgekozen)\s+(?:grens|regel)|"
                r"mental(?:e)?\s+stop)\b", result.text, re.I,
            ):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._stop_loss_coach_fallback(locale),
                    "safe_stop_loss_coaching", evidence,
                )
            if (
                _read_only_stop_loss_coaching(message)
                and (remaining := remaining_lifecycle_seconds()) is not None
                and remaining <= 5
            ):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._stop_loss_coach_fallback(locale),
                    "safe_stop_loss_coaching", evidence,
                )
            if (
                _read_only_stop_loss_coaching(message)
                and not any(item.get("scope") == "read_linked_strategy"
                            and item.get("status") == "completed" for item in evidence)
                and re.search(
                    r"\b(?:geen opgeslagen stop(?:niveau|.loss)?|geen stop.loss opgeslagen|"
                    r"no saved stop(?:.loss| level)?|keinen gespeicherten Stop)\b",
                    result.text, re.I,
                )
            ):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._stop_loss_coach_fallback(locale),
                    "safe_stop_loss_coaching", evidence,
                )
            objection = self._rule_objection_answer(
                message, str((previous_response or {}).get("answer") or ""), locale,
            )
            if objection and previous_response:
                return FinnResponsesVerifiedAnswer(
                    "completed", objection, "rule_objection_coaching", evidence, True,
                )
        if result.model_led_coach and self._unsupported_personal_confirmation(result.text, evidence, message):
            coach_fallback = self._emotional_coach_fallback(message, locale)
            if coach_fallback:
                return FinnResponsesVerifiedAnswer(
                    "completed", coach_fallback, "safe_emotional_coaching", evidence,
                )
            saved_plan_read = any(
                item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                and item.get("status") == "completed" for item in evidence
            )
            question = {
                "nl": ("De opgeslagen gegevens bevatten geen concrete bevestigingsvoorwaarde. "
                       if saved_plan_read else "Ik heb geen concrete bevestigingsvoorwaarde kunnen verifiëren. ")
                      + "Welke voorwaarde bedoel je precies?",
                "en": ("The saved data contains no specific confirmation condition. "
                       if saved_plan_read else "I haven't verified a specific confirmation condition. ")
                      + "Which condition do you mean?",
                "de": ("Die gespeicherten Daten enthalten keine konkrete Bestätigungsbedingung. "
                       if saved_plan_read else "Ich habe keine konkrete Bestätigungsbedingung verifiziert. ")
                      + "Welche Bedingung meinst du genau?",
            }[locale if locale in {"nl", "en", "de"} else "nl"]
            return FinnResponsesVerifiedAnswer(
                "clarification_required", question, "confirmation_condition_unverified", evidence,
                clarification={"question": question, "reason": "confirmation_condition_unverified"},
            )
        if not result.model_led_coach and any(item.get("reason") == "setup_ambiguous" for item in evidence) and not any(
            item.get("scope") == "read_active_setup" and item.get("status") == "completed"
            for item in evidence
        ):
            return FinnResponsesVerifiedAnswer(
                "clarification_required", self._fallback_copy("setup_ambiguous", message=message, locale=locale),
                "setup_ambiguous", evidence,
                clarification={
                    "question": self._fallback_copy("setup_ambiguous", message=message, locale=locale),
                    "reason": "setup_ambiguous",
                },
            )
        def missing_profile_clarification() -> FinnResponsesVerifiedAnswer | None:
            if not evidence or previous_response or not all(
                item.get("scope") in {"read_profile", "read_user_preferences"}
                for item in evidence
            ) or not any(
                item.get("scope") == "read_profile"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and item["data"].get("has_profile") is False
                for item in evidence
            ):
                return None
            question = {
                "nl": "Ik kan je helpen je plan en risico's te onderzoeken, maar ik mis nog je profiel om dat op jou af te stemmen. Wat is je belangrijkste doel en welke risicostijl past bij je?",
                "en": "I can help examine your plan and its risks, but I need your profile to tailor that to you. What is your main goal and risk style?",
                "de": "Ich kann dir helfen, deinen Plan und seine Risiken zu prüfen. Für eine persönliche Einordnung fehlt mir noch dein Profil. Was ist dein wichtigstes Ziel und welcher Risikostil passt zu dir?",
            }[locale if locale in {"nl", "en", "de"} else "nl"]
            return FinnResponsesVerifiedAnswer(
                "clarification_required", question, "user_detail_required", evidence,
                clarification={"question": question, "reason": "user_detail_required"},
            )
        compact = [
            {
                "scope": item.get("scope"), "status": item.get("status"),
                "source": item.get("source"),
                "as_of": item.get("as_of"), "asset": item.get("asset"),
                "freshness": item.get("freshness"), "availability": item.get("availability"),
                "data": item.get("data"), "reason": item.get("reason"),
            }
            for item in evidence
        ]
        direct_calls = [call for call in result.tool_trace if call.get("name") == "answer_directly"]
        if (
            not result.uses_previous_response and not result.tool_trace
        ) or (direct_calls and len(direct_calls) == len(result.tool_trace) and all(
            (call.get("arguments") or {}).get("uses_previous_response") is False
            for call in direct_calls
        )):
            previous_response = None
        previous_answer = str((previous_response or {}).get("answer") or "").strip()
        def quantities_supported(text: str) -> bool:
            user_question_context = "\n".join(filter(None, (
                str((previous_response or {}).get("user_message") or "")
                if reusing_previous_read else "",
                message,
            )))
            prior_quantity_context = (
                " ".join(part for part in (previous_answer, antecedent_answer) if part)
                if reusing_previous_read else previous_answer
            )
            return (
                self._amounts_supported(
                    answer=text, message=user_question_context, previous_answer=prior_quantity_context,
                    evidence=evidence,
                )
                and self._percentage_claims_supported(
                    answer=text, message=user_question_context, previous_answer=previous_answer,
                    evidence=evidence, response_focus=result.response_focus,
                )
                and self._static_risk_units_supported(text, evidence)
                and self._asset_quantities_supported(
                    answer=text, message=user_question_context, evidence=evidence,
                )
                and self._currency_units_supported(
                    answer=text, message=user_question_context, previous_answer=prior_quantity_context,
                    evidence=evidence,
                )
                and self._static_geometry_complete(text, evidence, result.response_focus)
                and not self._contains_internal_identifier(text)
                and not self._promises_unverified_trading_outcome(text)
                and not self._strategy_levels_attributed_to_setup(text, evidence)
                and self._saved_entity_type_supported(
                    text,
                    tuple((*evidence, *(relevant_previous_source_evidence if reusing_previous_read else ()))),
                    user_message=message,
                )
                and self._profile_presence_claim_supported(
                    text, tuple((*evidence, *relevant_previous_source_evidence)),
                )
                and self._saved_horizon_claim_supported(
                    text, tuple((*evidence, *relevant_previous_source_evidence)),
                )
                and not (
                    reusing_previous_read
                    and self._introduces_new_catalog_option(
                        text, previous_answer,
                        tuple((*evidence, *relevant_previous_source_evidence)),
                    )
                )
                and (not personal_evidence or not self._unevaluated_positive_fit_claim(text))
                and (not limited_evaluation or not self._unevaluated_positive_fit_claim(text))
                and (not personal_evidence or not self._ungrounded_level_advice(text))
            )
        confirmed_action = {
            key: recent_action_result.get(key)
            for key in ("operation_id", "entity_type", "canonical_name", "result_status")
            if recent_action_result and recent_action_result.get(key) is not None
        }
        general_education = (
            not result.tool_trace and not result.uses_previous_response
        ) or (bool(result.tool_trace) and all(
            call.get("name") == "answer_directly" for call in result.tool_trace
        ))
        evaluation_calls = [
            call for call in result.tool_trace
            if (call.get("result") or {}).get("evaluation_operation_id")
        ]
        limited_evaluation = any(
            (call.get("result") or {}).get("assessment_status") == "insufficient_evidence"
            and (call.get("result") or {}).get("evaluation_operation_id")
            != "evaluate_indicator_configuration"
            for call in evaluation_calls
        )
        plan_evaluation = any(
            (call.get("result") or {}).get("evaluation_operation_id")
            in {"evaluate_plan", "evaluate_setup", "evaluate_strategy"}
            for call in evaluation_calls
        )
        evaluation_target_ambiguous = any(
            item.get("availability") == "ambiguous"
            for call in evaluation_calls
            for item in (call.get("result") or {}).get("results") or []
            if isinstance(item, dict)
        )
        advice_diagnostics: dict[str, dict[str, Any]] = {}
        explicit_three_priorities = bool(re.search(
            r"\b(?:drie|three|drei|3)\s+(?:belangrijkste\s+|most important\s+|wichtigsten\s+)?"
            r"(?:acties|prioriteiten|stappen|actions|priorities|steps|Aktionen|Prioritäten|Schritte)\b",
            message, re.I,
        ))

        def limited_fallback() -> FinnResponsesVerifiedAnswer:
            if result.response_focus == "priorities" or explicit_three_priorities:
                has_strategy = any(
                    item.get("scope") == "read_linked_strategy"
                    and item.get("status") == "completed"
                    and isinstance(item.get("data"), dict)
                    and all(item["data"].get(field) for field in ("entry", "stop_loss", "targets"))
                    for item in evidence
                )
                market_unavailable = not any(
                    item.get("scope") == "read_market_snapshot"
                    and item.get("status") == "completed"
                    for item in evidence
                )
                if has_strategy and market_unavailable:
                    copy = {
                        "nl": (
                            "1. Controleer of de opgeslagen entry, stop-loss en doelen nog de niveaus zijn die jij bedoelt; dit is geen marktoordeel.\n"
                            "2. Bepaal welk maximaal verlies per positie binnen je eigen risicobudget past voordat je een inzet kiest.\n"
                            "3. Laat een nieuwe entrybeslissing open totdat een actuele bron jouw voorwaarden kan toetsen.\n"
                            "Laat liggen: verander geen opgeslagen niveaus en plaats geen order alleen uit FOMO."
                        ),
                        "en": (
                            "1. Check whether the saved entry, stop-loss and targets are still the levels you intend; this is not a market assessment.\n"
                            "2. Decide what maximum loss per position fits your risk budget before choosing a stake.\n"
                            "3. Leave a new entry decision open until current evidence can test your conditions.\n"
                            "Avoid: do not change saved levels or place an order just because of FOMO."
                        ),
                        "de": (
                            "1. Prüfe, ob der gespeicherte Einstieg, Stop-Loss und die Ziele noch deinen beabsichtigten Werten entsprechen; das ist keine Marktbeurteilung.\n"
                            "2. Bestimme vor einer Einsatzentscheidung, welcher maximale Verlust pro Position in dein Risikobudget passt.\n"
                            "3. Lass eine neue Einstiegsentscheidung offen, bis aktuelle Daten deine Bedingungen prüfen können.\n"
                            "Vermeide es, gespeicherte Werte zu ändern oder allein aus FOMO eine Order zu platzieren."
                        ),
                    }[locale if locale in {"nl", "en", "de"} else "nl"]
                    return FinnResponsesVerifiedAnswer(
                        "completed", copy, "insufficient_evidence", evidence, bool(previous_response),
                    )
            if result.response_focus == "review":
                saved_setup = next((
                    item.get("data") for item in evidence
                    if item.get("scope") == "read_active_setup"
                    and item.get("status") == "completed"
                    and isinstance(item.get("data"), dict)
                ), None)
                missing_strategy = any(
                    item.get("scope") == "read_linked_strategy"
                    and item.get("reason") == "strategy_not_resolved"
                    for item in evidence
                )
                if saved_setup and missing_strategy:
                    name = str(saved_setup.get("name") or "").strip()
                    has_market = any(
                        item.get("scope") == "read_market_snapshot"
                        and item.get("status") == "completed"
                        for item in evidence
                    )
                    phrases = {
                        "nl": (
                            "Wat vaststaat: Je setup{named} is opgeslagen.",
                            "Wat ik niet kan beoordelen: Voor deze setup is geen gekoppelde strategie gevonden{market}. "
                            "Ik kan daardoor geen afzonderlijke uitvoeringsregels of geschiktheid bevestigen.",
                            "Eerst kiezen: Wil je deze setup als zelfstandig plan bespreken of er een aparte strategie aan koppelen?",
                            "; ook actuele marktdata ontbreken" if not has_market else "",
                        ),
                        "en": (
                            "What is established: Your setup{named} is saved.",
                            "What I cannot assess: No linked strategy was found for this setup{market}. "
                            "I cannot verify separate execution rules or suitability from that.",
                            "Choose first: Do you want to discuss this setup as a standalone plan or link a separate strategy?",
                            "; current market data are also unavailable" if not has_market else "",
                        ),
                        "de": (
                            "Was feststeht: Dein Setup{named} ist gespeichert.",
                            "Was ich nicht beurteilen kann: Für dieses Setup wurde keine verknüpfte Strategie gefunden{market}. "
                            "Eigene Ausführungsregeln oder Eignung kann ich daraus nicht bestätigen.",
                            "Entscheide zuerst: Möchtest du dieses Setup als eigenständigen Plan besprechen oder eine separate Strategie verknüpfen?",
                            "; aktuelle Marktdaten fehlen ebenfalls" if not has_market else "",
                        ),
                    }[locale if locale in {"nl", "en", "de"} else "nl"]
                    named = f" ‘{name}’" if name else ""
                    proposed = self._proposed_change_copy(message=message, locale=locale)
                    proposed_next_step = {
                        "nl": "Eerst controleren: Welk deel van je beschikbare budget en bestaande blootstelling zou deze voorgestelde inleg innemen?",
                        "en": "Check first: How much of your available budget and existing exposure would this proposed contribution use?",
                        "de": "Prüfe zuerst: Welchen Anteil deines verfügbaren Budgets und deiner bestehenden Positionen würde dieser vorgeschlagene Betrag beanspruchen?",
                    }[locale if locale in {"nl", "en", "de"} else "nl"]
                    return FinnResponsesVerifiedAnswer(
                        "completed", "\n".join((
                            *([proposed] if proposed else []),
                            phrases[0].format(named=named),
                            phrases[1].format(market=phrases[3]),
                            proposed_next_step if proposed else phrases[2],
                        )),
                        "insufficient_evidence", evidence, bool(previous_response),
                    )
            missed_structure = "requested_structure_missing" in (
                advice_diagnostics.get(result.text, {}).get("rejected_checks") or []
            )
            saved_strategy = next((
                item.get("data") for call in evaluation_calls
                for item in (call.get("result") or {}).get("results", [])
                if item.get("scope") == "read_linked_strategy"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and all(item["data"].get(field) for field in ("entry", "stop_loss", "targets"))
            ), None)
            if saved_strategy:
                copy = {
                    "nl": (
                        "Sterk als vastgelegd controlepunt: je opgeslagen strategie bevat entry, stop-loss en doelen. "
                        "Ik rem je af bij een oordeel over geschiktheid: of die niveaus bij de markt en jouw risicobudget passen, kan ik met het beschikbare bewijs niet beoordelen. "
                        "Controleer eerst welke maximale verliesruimte per positie je hiervoor wilt aanhouden. "
                        "Je instellingen blijven ongewijzigd."
                    ),
                    "en": (
                        "What is established: your saved strategy has an entry, stop-loss and targets. "
                        "I cannot judge whether those levels fit the market and your risk budget from the available evidence. "
                        "What maximum loss per position do you want to allow? Your settings remain unchanged."
                    ),
                    "de": (
                        "Was feststeht: Deine gespeicherte Strategie enthält Einstieg, Stop-Loss und Ziele. "
                        "Ob diese Werte zum Markt und deinem Risikobudget passen, kann ich mit den verfügbaren Daten nicht beurteilen. "
                        "Welchen maximalen Verlust pro Position möchtest du zulassen? Deine Einstellungen bleiben unverändert."
                    ),
                }[locale if locale in {"nl", "en", "de"} else "nl"]
                return FinnResponsesVerifiedAnswer(
                    "completed", copy, "insufficient_evidence", evidence, bool(previous_response),
                )
            return FinnResponsesVerifiedAnswer(
                "unavailable" if missed_structure else "completed",
                self._limited_evaluation_copy(message=message, locale=locale),
                "responses_requested_structure_unverified" if missed_structure else "insufficient_evidence",
                evidence, bool(previous_response),
            )
        proposed_change = self._proposed_change_copy(message=message, locale=locale)
        if not result.model_led_coach and limited_evaluation and result.response_focus in {None, "general"} and proposed_change:
            proposed_amounts = self._currency_amounts(message)
            attributed = re.search(
                r"\b(?:je|jij|jouw|you|your|du|dein\w*)\b[^.!?\n]{0,65}"
                r"\b(?:overweeg\w*|denk\w*|consider\w*|propos\w*|erwäg\w*|überleg\w*)\b",
                result.text.casefold(),
            )
            if not proposed_amounts <= self._currency_amounts(result.text) or not attributed:
                return limited_fallback()
        for call in evaluation_calls:
            evaluation = call["result"]
            compact.append({
                "scope": "evaluation_boundary", "status": "completed",
                "source": "canonical_action_contract",
                "data": {
                    "operation_id": evaluation["evaluation_operation_id"],
                    "assessment_status": evaluation.get("assessment_status"),
                    "missing_required_scopes": evaluation.get("missing_required_scopes", []),
                    "resolved_entity_kinds": evaluation.get("resolved_entity_kinds", {}),
                },
            })
        verified_turn = project_verified_turn(previous_response)
        previous_source_evidence = list(verified_turn["evidence"]) if verified_turn else []
        previous_clarification_reason = (
            str((previous_response or {}).get("terminal_reason") or "")
            if (previous_response or {}).get("terminal_status") == "clarification_required"
            else ""
        )
        def prior_evaluation_explanation() -> FinnResponsesVerifiedAnswer | None:
            if not previous_explanation_only or previous_clarification_reason:
                return None
            evaluations = [
                call.get("result") or {}
                for call in (previous_response or {}).get("tool_trace", [])
                if (call.get("result") or {}).get("assessment_status") == "insufficient_evidence"
            ]
            if not any(
                "market_snapshot" in (item.get("missing_required_scopes") or [])
                for item in evaluations
            ):
                return None
            has_profile = any(
                item.get("scope") == "read_profile"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and item["data"].get("has_profile") is True
                for item in previous_source_evidence
            )
            copy = {
                "nl": (
                    "Ik kan nog niet beoordelen of dit plan bij je risicostijl past: actuele "
                    "marktgegevens ontbreken. Je opgeslagen risicoprofiel is wel beschikbaar; "
                    "zonder die marktgegevens zou een geschiktheidsconclusie speculatief zijn."
                    if has_profile else
                    "Ik kan dit plan nog niet beoordelen omdat actuele marktgegevens ontbreken. "
                    "Zonder die gegevens zou een geschiktheidsconclusie speculatief zijn."
                ),
                "en": (
                    "I can't assess whether this plan fits your risk style yet because current "
                    "market data is missing. Your saved risk profile is available, but a "
                    "suitability conclusion without that market data would be speculative."
                    if has_profile else
                    "I can't assess this plan yet because current market data is missing. "
                    "A suitability conclusion without it would be speculative."
                ),
                "de": (
                    "Ich kann noch nicht beurteilen, ob dieser Plan zu deinem Risikostil passt, "
                    "weil aktuelle Marktdaten fehlen. Dein gespeichertes Risikoprofil ist vorhanden; "
                    "ohne diese Marktdaten wäre ein Urteil über die Eignung spekulativ."
                    if has_profile else
                    "Ich kann diesen Plan noch nicht beurteilen, weil aktuelle Marktdaten fehlen. "
                    "Ohne sie wäre ein Urteil über die Eignung spekulativ."
                ),
            }[locale if locale in {"nl", "en", "de"} else "nl"]
            return FinnResponsesVerifiedAnswer(
                "completed", copy, "insufficient_evidence", evidence, True,
            )
        reusing_previous_read = bool(previous_response and previous_response.get("answer")) and (
            result.uses_previous_response or any(
                call.get("name") == "answer_directly"
                and dict(call.get("arguments") or {}).get("uses_previous_response") is True
                for call in result.tool_trace
            )
        )
        previous_explanation_only = (
            reusing_previous_read
            and (not result.tool_trace or all(
                call.get("name") == "answer_directly" for call in result.tool_trace
            ))
            and message.strip().casefold().rstrip("?!. ") in {
                "waarom", "why", "warum", "wieso", "weshalb",
            }
        )
        current_scopes = {item.get("scope") for item in evidence}
        limited_plan_review = result.response_focus == "review" and any(
            (call.get("result") or {}).get("evaluation_operation_id") == "evaluate_plan"
            and (call.get("result") or {}).get("assessment_status") == "insufficient_evidence"
            for call in result.tool_trace
        )
        completed_scopes = {
            item.get("scope") for item in evidence if item.get("status") == "completed"
        }
        relevant_previous_source_evidence = [
            item for item in previous_source_evidence
            if item.get("scope") not in completed_scopes
            and (
                item.get("status") == "completed"
                or not current_scopes
                or item.get("scope") in current_scopes
            )
        ]
        saved_horizon_objects = [
            item["data"] for item in (*evidence, *relevant_previous_source_evidence)
            if item.get("scope") in {"read_active_setup", "read_linked_strategy"}
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
        ]
        answering_horizon_clarification = (
            (
                result.resumed_clarification_reason == "investment_horizon_required"
                or previous_clarification_reason == "investment_horizon_required"
            )
            and bool(re.search(
                r"\b(?:langetermijn\w*|lange termijn|jaar|jaren|maanden|long.term|years?|months?|"
                r"langfristig\w*|Jahre?|Monate?|swing.?trade|kortetermijn\w*|short.term)\b",
                message, re.I,
            ))
        )
        if answering_horizon_clarification and (
            not result.model_led_coach
            or result.text.rstrip().endswith("?")
            or not re.search(
                r"\b(?:langetermijn\w*|lange termijn|long.term|langfristig\w*)\b",
                result.text, re.I,
            )
        ):
            return FinnResponsesVerifiedAnswer(
                "completed", self._horizon_detail_acknowledgement(
                    message, tuple((*evidence, *relevant_previous_source_evidence)), locale,
                ), "user_detail_acknowledged", evidence, True,
            )
        asks_horizon_classification = result.horizon_classification_question or bool(
            re.search(r"\b(?:langetermijn\w*|lange termijn|swing.?trade|long.term|short.term|langfristig\w*)\b", message, re.I)
            and re.search(r"\b(?:setup|plan|timeframe|4H|grafiek)\b", message, re.I)
            and "?" in message
        )
        if not answering_horizon_clarification and asks_horizon_classification and saved_horizon_objects and not any(
            data.get(field) for data in saved_horizon_objects
            for field in ("investment_horizon", "holding_period", "trade_horizon")
        ):
            question = self._horizon_clarification_copy(locale)
            return FinnResponsesVerifiedAnswer(
                "clarification_required", question, "investment_horizon_required", evidence,
                clarification={"question": question, "reason": "investment_horizon_required"},
            )
        if not limited_plan_review and not self._saved_horizon_claim_supported(
            result.text, tuple((*evidence, *relevant_previous_source_evidence)),
        ):
            if previous_answer and message.strip() and not message.rstrip().endswith("?"):
                return FinnResponsesVerifiedAnswer(
                    "completed", self._horizon_detail_acknowledgement(
                        message, tuple((*evidence, *relevant_previous_source_evidence)), locale,
                    ),
                    "user_detail_acknowledged", evidence, True,
                )
            question = self._horizon_clarification_copy(locale)
            return FinnResponsesVerifiedAnswer(
                "clarification_required", question, "investment_horizon_required", evidence,
                clarification={"question": question, "reason": "investment_horizon_required"},
            )
        compact.extend({
            "scope": item.get("scope"), "status": item.get("status"),
            "source": item.get("source"), "as_of": item.get("as_of"),
            "asset": item.get("asset"), "freshness": item.get("freshness"),
            "availability": item.get("availability"), "data": item.get("data"),
            "reason": item.get("reason"), "lineage": "previous_verified_run",
        } for item in relevant_previous_source_evidence if item.get("status") == "completed"
        or (reusing_previous_read and item.get("status") in {"unavailable", "stale", "error"}))
        unavailable_without_cause = any(
            item.get("reason") == "source_unavailable"
            for item in (*evidence, *relevant_previous_source_evidence)
        )
        limitation_only = bool(evidence) and all(item.get("status") != "completed" for item in evidence)
        missing_profile_established = any(
            item.get("scope") == "read_profile"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and item["data"].get("has_profile") is False
            for item in evidence
        )
        profile_only = bool(evidence) and all(
            item.get("scope") in {"read_profile", "read_user_preferences"}
            for item in evidence
        )
        resolving_choice = message.startswith("Original user request:") and "User's chosen answer:" in message
        if resolving_choice and not self._answered_duration_preserved(message, result.text):
            return FinnResponsesVerifiedAnswer(
                "completed", self._horizon_detail_acknowledgement(
                    message, tuple((*evidence, *relevant_previous_source_evidence)), locale,
                ),
                "user_detail_acknowledged", evidence, True,
            )
        antecedent_answer = str((previous_response or {}).get("antecedent_verified_answer") or "").strip()
        if previous_answer and not resolving_choice:
            compact.append({
                "scope": "previous_response",
                "source": "owner_scoped_runtime_contract",
                "availability": "available",
                "data": {
                    "answer": previous_answer,
                    "terminal_reason": previous_clarification_reason or None,
                    "source_evidence": [] if previous_explanation_only else relevant_previous_source_evidence,
                },
            })
            if antecedent_answer and not previous_explanation_only:
                compact.append({
                    "scope": "antecedent_verified_response",
                    "source": "owner_scoped_runtime_contract",
                    "availability": "available",
                    "data": {"answer": antecedent_answer},
                })
        if previous_explanation_only:
            compact = [
                item for item in compact
                if item.get("scope") in {"previous_response", "read_profile"}
            ]
        if confirmed_action.get("result_status") == "succeeded":
            compact.append({
                "scope": "confirmed_action_result",
                "source": "owner_scoped_runtime_contract",
                "availability": "available",
                "data": confirmed_action,
            })
        guidance = (
                "This is a Responses-tool-loop answer, not a selector-first contract response. "
                "The effective answer language is "
                + ({"nl": "Dutch", "en": "English", "de": "German"}.get(locale or "", "Dutch"))
                + ", selected from the owner's preference and any explicit language switch. "
                "Judge the draft's language against this effective language, not against the "
                "language of the latest user message alone. "
                "Check every concrete personal or market fact against the supplied typed tool evidence, "
                "including asset, timeframe, freshness and unavailable states. Preserve field meaning "
                "and units: a percentage allocation is not a currency balance, a saved budget is not "
                "available cash, and missing values are not zero. Speak to the user, never narrate "
                "their request in third person as if writing an internal report. An evaluation_boundary "
                "with assessment_status=insufficient_evidence is a registry-derived limitation, not a "
                "completed personal risk judgment. The answer may describe verified saved facts and "
                "missing sources but must not claim that a plan fits the user's risk style. "
                "If owner-scoped profile evidence confirms has_profile=true, never say the risk "
                "profile, risk style or its information is unavailable; distinguish missing live "
                "market evidence from the present saved profile. General educational explanations "
                "and an honest statement that personal data is unavailable do not require "
                "unrelated extra tools or a fully populated profile. A conditional description "
                "of FINN capabilities may name concrete kinds of help without a profile or saved "
                "plan read; it is not a claim that this user has saved those objects. Require "
                "evidence if the answer asserts their existence, values, current state or personal "
                "suitability. Do not strip concrete capability examples merely to avoid an "
                "unsupported saved-object claim. Do not demand every possible "
                "scope when the answer explicitly limits itself to available evidence. If a previous "
                "verified response appears in evidence, interpret short follow-up questions relative "
                "to that response, but reject invented causes, technical failures or unsupported advice. "
                "A prior verified response may establish what the user said or asked, even when "
                "that statement is not a saved plan field. The assistant may explain a user-stated "
                "condition as user-stated; only claims that it is persisted, currently satisfied, "
                "or proven to improve an outcome require separate typed evidence. "
                "A saved setup or strategy proves its stored fields, not that those fields were "
                "derived from earlier analysis; reject an asserted analysis history unless the "
                "typed evidence contains it. "
                "A completed level_geometry inside a completed owner-scoped "
                "read_linked_strategy is verified static arithmetic from saved entry, stop "
                "and targets. An answer may state its per-unit risk and per-target reward-to-risk "
                "ratios even when live market scopes are unavailable. If the user asks for "
                "that static calculation, do not replace it with only a missing-data warning. "
                "The ratios do not prove current entry conditions, profitability or personal fit. "
                "A chart timeframe such as 4H and a DCA cadence do not establish a holding "
                "horizon or make this owner's setup a swing-trading or long-term plan. Reject "
                "a personalized classification or recommendation inferred from chart timeframe "
                "without explicit owner-scoped horizon and evaluation evidence. "
                + (
                    "The latest user message answers FINN's preceding question. The answer must "
                    "acknowledge the newly supplied detail as a user-stated preference, not a "
                    "persisted plan field or an evaluated suitability conclusion. Do not replace "
                    "this turn with a recap of older missing-market-data advice. A bare echo or "
                    "meta acknowledgement of the user's words is insufficient: connect the new "
                    "detail to the question FINN was trying to resolve, within the available "
                    "evidence, and state any remaining limit without inventing a conclusion. "
                    if result.answer_kind == "answers_previous_question" else ""
                )
                + "For a short why follow-up, reject a mere recap of stored fields or a repetition "
                "of the same user question. Require an actual evidence-grounded explanation of "
                "the prior conclusion or why the previously requested detail is needed."
                " When a user asks for a personalized logical trading plan but the supplied "
                "evidence contains only saved profile/setup/strategy choices and no completed "
                "current market or owner-scoped risk evaluation, a short answer that names the "
                "verified saved settings, explicitly declines to judge suitability yet, and asks "
                "whether to perform the missing assessment IS a complete, safe answer. Do not "
                "fail it for not producing a trade recommendation; producing one would be unsafe. "
                " A stored entry, stop-loss, target or amount establishes only its configured value. "
                "A read_active_setup result describes a setup, never a strategy. If the "
                "read_linked_strategy result is unavailable, reject any answer that calls the "
                "setup a saved strategy or claims that a linked strategy exists. "
                "It does not establish that the trade is prudent, profitable, realistic or suitable "
                "for this user. Reject those conclusions without current market and risk evidence. "
                "For example, an answer that turns a configured stop-loss into a recommendation to "
                "move it as prices rise, or calls a target logical or risk-controlled, is unsupported "
                "unless the supplied evidence proves that specific advice. A profile label and stored "
                "strategy fields alone are not enough. In particular, claiming that a saved setup "
                "is well aligned with the user's balanced risk profile or wealth-building goal "
                "requires an actual owner-scoped risk calculation or plan evaluation result, not "
                "just matching labels. Reject such a fit conclusion when that evidence is absent."
                " A completed owner-scoped read_profile with has_profile=false proves that profile "
                "goals and risk style are not saved. It supports a brief explanation that personal "
                "plan suitability cannot yet be assessed and a request for that user choice; it does "
                "not support inventing the missing profile or endorsing a trade. When the user asks "
                "what FINN can help with based on that absent profile, a factual statement of this "
                "limitation plus a request for the missing profile choice IS a complete, supported "
                "answer. Do not fail it merely because no personal recommendations are possible."
                " Judge source availability per claim and question, not per bundled tool. A completed "
                "owner-scoped indicator_configuration with an empty category list proves that the "
                "user has no saved indicators in that category. An unavailable technical or market "
                "snapshot does not invalidate that configuration fact or ordinary educational reasons "
                "for considering a category; it only prevents claims about current indicator values "
                "or market effects. Conversely, never infer a current value from saved configuration."
                " A read_asset_scores item with a dated as_of and freshness=stale may support "
                "reporting its exact historical score values when the answer names that date "
                "and clearly says they are not current. Do not treat a historical score as a "
                "current market snapshot, personal suitability judgment, or trading signal. "
                "Reject invented score values or an undated claim that those values hold now. "
                " Active indicator options supplied by the canonical indicator catalog can ground "
                "a recommendation of what to configure next, but not a claim about its current reading. "
                "The available_macro_indicator_catalog scope lists supported options that are "
                "deliberately NOT in the user's saved configuration; recommending one of them "
                "does not claim it is already saved. If the user asks which single indicator "
                "to consider next, enumerating the whole catalog does not answer the question. "
                "Require one supported, not-yet-configured choice with a short general reason "
                "and no unsupported current reading or market-effect claim."
                " A confirmed_action_result is verified persisted evidence of the object just saved. "
                "For a claim about which object was saved, its exact canonical_name must match this "
                "result; a short guided slot answer is not an object's name unless this result says so. "
                "Do not invent saved object names from conversation text. This action result proves "
                "only object identity and successful persistence, not its current asset, timeframe, "
                "frequency, amount, currency or other fields. Previous chat text and a draft are "
                "not a saved-object read. If an answer describes any such object fields, require a "
                "completed owner-scoped read of that object type in the current tool trace, "
                "or an immediately preceding verified owner-scoped read when this direct "
                "follow-up explicitly references that previous response and makes no new field claim; "
                "read_review_history and read_latest_report do not satisfy setup/strategy/bot "
                "field claims. Reject unsupported extra details even when the saved name is correct."
                " If the preceding response asked the user to choose a setup and the current "
                "read_active_setup result is completed for that chosen name, the choice is resolved. "
                "Reject an answer that asks the user to choose the same setup again; the answer "
                "must address the original request using the resolved evidence."
                " Also verify that the answer addresses the user's actual request. If the user explicitly "
                "asked to create, update or delete a saved object, a read-only explanation or request "
                "for profile details does not fulfill that action request. Reject it so FINN can retry "
                "with the registry-backed proposal tool; missing action inputs are collected by that tool."
                " When typed tools report unavailable or stale, an answer that accurately states "
                "the limitation and does not invent prices, dates or conclusions is supported by "
                "that unavailable evidence; source_unavailable alone is not a reason to reject it."
                " A typed object *_not_resolved reason establishes only that no unique owner-scoped "
                "object was identified. It supports saying that no linked object can be shown, "
                "not an asserted provider outage or access failure."
                + (
                    " All requested tool sources are unavailable here. Verify whether the answer "
                    "only acknowledges that limitation for the requested assets and refrains from "
                    "invented prices, dates, causes, financial conclusions or advice. Such a limited "
                    "answer is fully supported by these typed unavailable results and should pass."
                    if limitation_only else ""
                )
                + (
                    " The typed source_unavailable reason establishes only that current data cannot "
                    "be read. It does NOT establish a technical outage, provider failure, temporary "
                    "disruption, or any other cause. Reject any asserted cause unless it is separately "
                    "and explicitly evidenced by a tool result."
                    if unavailable_without_cause else ""
                )
                + (
                    " This is a direct answer without a FINN tool call. "
                    "Check ordinary conceptual accuracy and absence of personal or current-market claims. "
                    "For RSI, overbought and oversold describe momentum conditions; they do not "
                    "by themselves prove that an asset is objectively too expensive or too cheap. "
                    "Do not require any profile, plan, market or owner-scoped evidence for a general definition."
                    if general_education else ""
                )
        )
        if previous_clarification_reason and reusing_previous_read:
            guidance += (
                " The immediately previous verified response was a clarification request "
                f"with typed reason {previous_clarification_reason}. The current user asks "
                "about that clarification, not for the original financial assessment. "
                "Verify whether the answer explains or restates why the choice is needed. "
                "Do not require a profile, live market data, or a completed plan evaluation "
                "merely to explain a choice request. Still reject invented facts about the "
                "user's profile or a claim that any particular setup is suitable."
            )
        if result.model_led_coach:
            language = {"nl": "Dutch", "en": "English", "de": "German"}.get(locale or "", "Dutch")
            guidance = (
                "Verify this model-led FINN answer against the typed owner-scoped evidence and "
                "the user's actual question. The effective answer language is " + language + "; "
                "judge that language, not against the language of the latest user message alone. "
                "Require evidence for claims about this user's saved objects, profile, balances, "
                "current prices, indicator values, or suitability. Check asset, timeframe, source, "
                "as_of, availability and units. A conditional description of FINN capabilities "
                "or a general explanation needs no owner read, but must not imply saved user data. "
                "A user-stated rule is not a persisted rule; it can be explained conditionally "
                "without claiming that it improves outcomes. A user's description of a market "
                "move is not a verified current quote or trend: reject an unqualified statement "
                "that the move is real when no current market evidence was returned. Static calculations from verified "
                "saved entry, stop and targets are allowed, but do not prove a live trade signal. "
                "For a partial result, answer the supported part and state the specific limit; "
                "do not demand unrelated evidence or replace a useful partial answer with only "
                "a missing-data statement. A setup_ambiguous result means no unique owner-scoped "
                "setup was identified: ask which one matters, but do not claim a number of matches "
                "unless the tool returned a count. A typed object *_not_resolved reason means no unique "
                "owner-scoped object was identified, not a provider outage. Use the typed "
                "reasons and registry operations in the summary: unresolved is not nonexistent, "
                "and an unsupported feature is not a data outage. Unavailable or stale "
                "market data cannot support a current reading or an invented failure cause. "
                "A completed read_active_setup identifies the active setup even when other setups "
                "are listed; it does not require a new choice. Owner-scoped report_not_found "
                "establishes that no saved report was found, not a provider failure. A completed "
                "read_review_history with items=[] establishes an empty saved history. Do not "
                "treat either absence as an unexplained source outage. "
                "A verified previous clarification may be explained without redoing the original "
                "financial assessment. Reject invented personal or market facts, unverified "
                "profit or safety promises, advice to bypass a user precaution, a write claim "
                "without confirmed execution, or an autonomous broker/live-bot action."
            )
        mode = (
            "EVALUATE" if evaluation_calls else
            "EXPLAIN" if (previous_answer and not resolving_choice) or general_education else
            "UNAVAILABLE" if limitation_only or (missing_profile_established and profile_only) else
            "READ"
        )
        user_message = message
        summary = {
            "available_scopes": [item.get("scope") for item in evidence if item.get("status") == "completed"]
            + (["previous_response"] if previous_answer else [])
            + (["confirmed_action_result"] if confirmed_action.get("result_status") == "succeeded" else []),
            "unavailable_scopes": [item.get("scope") for item in evidence if item.get("status") != "completed"],
            "unavailable_cause_established": False if unavailable_without_cause else None,
            "typed_unavailable_reasons": [
                {"scope": item.get("scope"), "reason": item.get("reason")}
                for item in evidence
                if item.get("status") != "completed" and item.get("reason")
            ],
            "registered_operations": [
                contract.operation_id for contract in FinnV2OperationRegistry().list()
            ],
            "general_education_no_personal_claims": general_education,
            "previous_verified_answer": previous_answer or None,
            "previous_user_message": (verified_turn or {}).get("user_message"),
            "static_level_geometry": [
                item["data"]["level_geometry"]
                for item in evidence
                if item.get("scope") == "read_linked_strategy"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and isinstance(item["data"].get("level_geometry"), dict)
                and item["data"]["level_geometry"].get("status") == "completed"
            ],
        }
        if missing_profile_established:
            summary["missing_profile_established"] = True
        if limited_evaluation:
            summary["evaluation_incomplete"] = True
        if previous_clarification_reason and reusing_previous_read:
            summary["previous_clarification_reason"] = previous_clarification_reason
            summary["current_request_scope"] = "explain_or_restate_previous_clarification"
        if resolving_choice:
            summary["permitted_limited_answer"] = (
                "Describe verified saved configuration, explicitly withhold any suitability "
                "judgment without a current market/risk evaluation, and offer that assessment."
            )
        personal_evidence = any(
            item.get("status") == "completed"
            and (
                item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                or (
                    item.get("scope") == "read_profile"
                    and isinstance(item.get("data"), dict)
                    and item["data"].get("has_profile") is True
                )
            )
            for item in (*evidence, *(relevant_previous_source_evidence if reusing_previous_read else []))
        )
        review_has_missing_plan_component = (
            result.response_focus == "review"
            and any(
                call.get("result", {}).get("evaluation_operation_id") == "evaluate_plan"
                for call in evaluation_calls
            )
            and any(item.get("scope") == "read_active_setup" and item.get("status") == "completed"
                    for item in evidence)
            and any(item.get("scope") == "read_linked_strategy" and item.get("status") != "completed"
                    for item in evidence)
        )
        unavailable_technical = any(
            item.get("scope") == "read_technical_snapshot"
            and item.get("status") != "completed"
            for item in evidence
        )
        unavailable_live_for_priorities = (
            (result.response_focus == "priorities" or explicit_three_priorities)
            and not any(item.get("scope") == "read_market_snapshot"
                        and item.get("status") == "completed" for item in evidence)
        )
        if (
            result.model_led_coach and explicit_three_priorities
            and limited_evaluation and plan_evaluation and unavailable_live_for_priorities
            and any(
                item.get("scope") == "read_linked_strategy"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and all(item["data"].get(field) for field in ("entry", "stop_loss", "targets"))
                for item in evidence
            )
        ):
            return limited_fallback()
        advice_evidence = [
            item for item in compact
            if item.get("status") in {"completed", "unavailable", "stale", "error"}
            and (
                item.get("lineage") != "previous_verified_run"
                or item.get("scope") == "read_profile"
                or reusing_previous_read
            )
        ]
        no_linked_strategy_evidence = any(
            item.get("scope") == "read_linked_strategy"
            and item.get("status") in {"unavailable", "stale", "error"}
            for item in advice_evidence
        ) and not any(
            item.get("scope") == "read_linked_strategy"
            and item.get("status") == "completed"
            for item in advice_evidence
        )

        advice_cache: dict[str, bool] = {}
        technical_cache: dict[str, bool] = {}
        catalog_cache: dict[str, tuple[bool, str]] = {}
        catalog_options = [
            {"name": str(option.get("name") or ""),
             "display_name": str(option.get("display_name") or "")}
            for item in evidence if item.get("scope") == "available_macro_indicator_catalog"
            for option in (item.get("data") or {}).get("supported_options", [])
            if isinstance(option, dict)
        ]
        if not any(
            call.get("name") in {"get_indicator_snapshot", "evaluate_indicator_configuration"}
            for call in result.tool_trace
        ):
            catalog_options = []

        async def advice_supported(text: str) -> bool:
            if not personal_evidence or self.client is None:
                return True
            if text not in advice_cache:
                details: dict[str, Any] = {}
                advice_diagnostics[text] = details
                audited = True
                if not result.model_led_coach and not previous_explanation_only:
                    audited = await self._personal_advice_is_grounded(
                        answer=text, evidence=advice_evidence,
                        remaining=remaining_lifecycle_seconds(),
                        question=message,
                        previous_answer=(
                            "\n".join(part for part in (antecedent_answer, previous_answer) if part)
                            if reusing_previous_read else None
                        ),
                        require_address_judgment=result.answer_kind != "grounded_next_decision",
                        require_actionable_next_decision=(
                            result.answer_kind == "grounded_next_decision"
                            or review_has_missing_plan_component
                            or result.response_focus == "priorities"
                        ),
                        answering_previous_question=result.answer_kind == "answers_previous_question",
                        conditional_process=result.answer_kind == "conditional_process",
                        locale=locale,
                        audit_diagnostics=details,
                    )
                if audited:
                    claim_trace = tuple(result.tool_trace) + tuple(
                        (previous_response or {}).get("tool_trace") or ()
                    )
                    claim_boundary = await FinnV2HardClaimBoundary().assess(
                        answer=text, tool_trace=claim_trace,
                        recent_action_result=recent_action_result,
                        user_message="\n".join(filter(None, (
                            str((previous_response or {}).get("user_message") or ""), message,
                        ))),
                    )
                    details["claim_boundary_available"] = claim_boundary.available
                    details["claim_boundary_violations"] = list(claim_boundary.violations)
                    details["claim_boundary_quotes"] = {
                        key: quote for key, quote in claim_boundary.quotes.items()
                        if quote and key.removesuffix("_quote") in claim_boundary.violations
                    }
                    audited = claim_boundary.available and not claim_boundary.violations
                advice_cache[text] = audited or bool(
                    result.model_led_coach
                    and details.get("audit_unavailable")
                    and quantities_supported(text)
                    and not self._unevaluated_positive_fit_claim(text)
                    and not self._ungrounded_level_advice(text)
                    and not self._promises_unverified_trading_outcome(text)
                    and self._proposal_speaker_is_user(text)
                    and self._assistant_does_not_claim_user_mutation(text)
                )
            return advice_cache[text]

        def claim_failure_reason() -> str | None:
            violations = advice_diagnostics.get(result.text, {}).get("claim_boundary_violations") or []
            if "personal_fit" in violations:
                return "personal_fit_not_established"
            if "current_market" in violations:
                return "current_market_claim_unverified"
            if "claimed_saved_action" in violations:
                return "saved_action_claim_unverified"
            if "outcome_claim" in violations:
                return "trading_outcome_claim_unverified"
            if "condition_bypass" in violations:
                return "user_condition_bypass_blocked"
            if not self._saved_entity_type_supported(
                result.text,
                tuple((*evidence, *(relevant_previous_source_evidence if reusing_previous_read else ()))),
                user_message=message,
            ):
                return "saved_entity_type_unverified"
            return None

        async def technical_supported(text: str) -> bool:
            if not unavailable_technical or result.model_led_coach:
                return True
            if text not in technical_cache:
                technical_cache[text] = await self._technical_limitation_is_grounded(
                    answer=text, remaining=remaining_lifecycle_seconds(),
                )
            return technical_cache[text]

        async def catalog_focused(text: str) -> bool:
            if result.model_led_coach:
                return True
            if not catalog_options:
                return True
            if text not in catalog_cache:
                catalog_cache[text] = await self._catalog_answer_is_focused(
                    question=user_message, answer=text, options=catalog_options,
                    remaining=remaining_lifecycle_seconds(),
                )
            return catalog_cache[text][0]

        def presentation_ok(text: str) -> bool:
            if result.model_led_coach:
                return (
                    self._language_matches(text, locale)
                    and self._assistant_does_not_claim_user_mutation(text)
                    and self._proposal_speaker_is_user(text)
                )
            personal_profile_read = any(
                item.get("scope") == "read_profile" and item.get("status") == "completed"
                for item in evidence
            )
            factual_score_list = self._factual_score_list_requested(message, evidence)
            return (
                self._language_matches(text, locale)
                and (not evidence or self._avoids_internal_user_frame(text))
                and self._assistant_does_not_claim_user_mutation(text)
                and (not evaluation_calls or not self._currency_amounts(message)
                     or self._currency_amounts(message) <= self._currency_amounts(text))
                and (not evaluation_calls or self._proposal_speaker_is_user(text))
                and (result.answer_kind != "grounded_next_decision"
                     or not self._asks_user_to_supply_unavailable_source(text))
                and (not unavailable_without_cause
                     or not self._asks_user_to_supply_unavailable_source(text))
                and (not unavailable_live_for_priorities
                     or not self._uses_unavailable_live_source_as_current_action(text))
                and (not message.startswith("Original user request:")
                     or self._evaluation_presentation_is_coaching(text))
                and
                (factual_score_list or result.model_led_coach
                 or not evaluation_calls and not personal_profile_read
                 and result.answer_kind != "grounded_next_decision"
                 or self._evaluation_presentation_is_coaching(
                     text, requested_list=result.response_focus == "priorities",
                 ))
                and (not any(
                    call["result"].get("assessment_status") == "insufficient_evidence"
                    for call in evaluation_calls
                ) or evaluation_target_ambiguous or not self._reoffers_attempted_evaluation(text))
                and self._followup_advances_conversation(message, previous_answer, text)
            )

        async def typed_next_decision_fallback() -> FinnResponsesVerifiedAnswer | None:
            if not (
                result.answer_kind == "grounded_next_decision"
                and previous_answer
                and any(
                    (call.get("result") or {}).get("assessment_status") == "insufficient_evidence"
                    for call in (previous_response or {}).get("tool_trace", [])
                )
            ):
                return None
            language = locale if locale in {"nl", "en", "de"} else self._fallback_language(message, previous_answer)
            grounded_choice = {
                "nl": "Je eerste keuze is om je opgeslagen setup voorlopig ongewijzigd te laten. Verander hem pas wanneer de ontbrekende actuele gegevens een beoordeling mogelijk maken.",
                "en": "Your first choice is to leave your saved setup unchanged for now. Only consider changing it once the missing current data allows an assessment.",
                "de": "Deine erste Entscheidung ist, dein gespeichertes Setup vorerst unverändert zu lassen. Ändere es erst, wenn die fehlenden aktuellen Daten eine Beurteilung erlauben.",
            }[language]
            if quantities_supported(grounded_choice) and presentation_ok(grounded_choice):
                return FinnResponsesVerifiedAnswer("completed", grounded_choice, None, evidence, True)
            return None

        async def verify_text(text: str):
            return await self.semantic.verify_async(
                mode=mode, user_message=user_message, mandatory=True,
                verification_guidance=guidance,
                sanitized_draft={"mode": mode, "direct_answer": text},
                compact_evidence=compact, deterministic_summary=summary,
                coach_answer=result.model_led_coach,
            )

        verdict, advice_ok, technical_ok, catalog_ok = await asyncio.gather(
            verify_text(result.text),
            advice_supported(result.text),
            technical_supported(result.text),
            catalog_focused(result.text),
        )
        verdict_passes = verdict.passes if result.model_led_coach else (
            verdict.passes or (
                not previous_explanation_only and personal_evidence
                and self.client is not None and advice_ok
            )
        )
        partial_evaluation_scopes = {
            item.get("scope") for item in evidence
            if item.get("status") == "completed"
        }
        independently_audited_limit = (
            bool(evaluation_calls)
            and all(
                call["result"].get("assessment_status") == "insufficient_evidence"
                for call in evaluation_calls
            )
            and {"read_profile", "read_active_setup"} <= partial_evaluation_scopes
            and self.client is not None
            and advice_ok
            and not previous_explanation_only
        )
        verification_available = verdict.available if result.model_led_coach else (
            verdict.available or independently_audited_limit
        )
        if verdict.available and not catalog_ok and catalog_options and not result.model_led_coach:
            focused_replacement = catalog_cache.get(result.text, (False, ""))[1]
            if focused_replacement:
                focused_verdict = await verify_text(focused_replacement)
                configured_macro = next((
                    item.get("data", {}).get("macro", [])
                    for item in evidence
                    if item.get("scope") == "read_indicator_configuration"
                    and item.get("status") == "completed"
                    and isinstance(item.get("data"), dict)
                ), None)
                mentioned_options = [
                    option for option in catalog_options
                    if str(option.get("display_name") or "").casefold()
                    in focused_replacement.casefold()
                ]
                configured_names = {
                    str(item.get("indicator") or "").casefold()
                    for item in (configured_macro or []) if isinstance(item, dict)
                }
                catalog_gap_grounded = (
                    configured_macro is not None
                    and len(mentioned_options) == 1
                    and str(mentioned_options[0].get("name") or "").casefold()
                    not in configured_names
                    and self._assistant_does_not_claim_user_mutation(focused_replacement)
                    and not re.search(
                        r"\b(?:je\s+overweegt|you\s+are\s+considering|du\s+erwägst)\b",
                        focused_replacement, re.IGNORECASE,
                    )
                    and presentation_ok(focused_replacement)
                )
                logger.info(
                    "FINN catalog focus repair checked: semantic=%s gap=%s quantities=%s codes=%s",
                    focused_verdict.passes, catalog_gap_grounded,
                    quantities_supported(focused_replacement),
                    list(focused_verdict.reason_codes),
                )
                if (
                    focused_verdict.available and (focused_verdict.passes or catalog_gap_grounded)
                    and quantities_supported(focused_replacement)
                    and await advice_supported(focused_replacement)
                    and await technical_supported(focused_replacement)
                ):
                    return FinnResponsesVerifiedAnswer(
                        "completed", focused_replacement, None, evidence, bool(previous_answer),
                    )
            else:
                logger.info("FINN catalog focus repair produced no valid single-option answer")
        if not result.model_led_coach and limited_evaluation and result.response_focus == "review" and any(
            call["result"].get("evaluation_operation_id") == "evaluate_plan"
            for call in evaluation_calls
        ):
            return limited_fallback()
        if not verification_available or not verdict_passes or not quantities_supported(result.text) or not advice_ok or not technical_ok or not catalog_ok or not presentation_ok(result.text):
            if result.model_led_coach:
                if any(item.get("reason") == "setup_ambiguous" for item in evidence) and not any(
                    item.get("scope") == "read_active_setup" and item.get("status") == "completed"
                    for item in evidence
                ):
                    question = self._fallback_copy("setup_ambiguous", message=message, locale=locale)
                    return FinnResponsesVerifiedAnswer(
                        "clarification_required", question, "setup_ambiguous", evidence,
                        clarification={"question": question, "reason": "setup_ambiguous"},
                    )
                logger.info(
                    "FINN model-led answer rejected: codes=%s available=%s semantic_pass=%s quantities=%s advice=%s technical=%s presentation=%s",
                    list(verdict.reason_codes), verdict.available, verdict.passes,
                    quantities_supported(result.text), advice_ok, technical_ok,
                    presentation_ok(result.text),
                )
                reason = claim_failure_reason() or "responses_evidence_not_verified"
                if answering_horizon_clarification and reason == "personal_fit_not_established":
                    return FinnResponsesVerifiedAnswer(
                        "completed", self._horizon_detail_acknowledgement(
                            message, tuple((*evidence, *relevant_previous_source_evidence)), locale,
                        ), "user_detail_acknowledged", evidence, True,
                    )
                rejected_quotes = advice_diagnostics.get(result.text, {}).get("claim_boundary_quotes") or {}
                verified_entities = [
                    entity_type for entity_type, scope in (
                        ("setup", "read_active_setup"), ("strategy", "read_linked_strategy"),
                    )
                    if any(item.get("scope") == scope and item.get("status") == "completed"
                           for item in evidence)
                ]
                rejection_details = (
                    {"unsupported_claims": rejected_quotes} if rejected_quotes else {}
                )
                if reason == "saved_entity_type_unverified":
                    rejection_details["verified_entity_types"] = verified_entities
                # A factually verified answer in the wrong language can be
                # rewritten using the same typed evidence below. Keep every
                # other model-led rejection on the fail-closed path.
                language_only_repair = (
                    verification_available and verdict_passes
                    and quantities_supported(result.text) and advice_ok
                    and technical_ok and catalog_ok
                    and not self._language_matches(result.text, locale)
                    and self._assistant_does_not_claim_user_mutation(result.text)
                    and self._proposal_speaker_is_user(result.text)
                )
                if not language_only_repair:
                    review_fallback = self._grounded_plan_review_fallback(
                        message, evidence, locale,
                    )
                    if review_fallback:
                        return FinnResponsesVerifiedAnswer(
                            "completed", review_fallback, "grounded_plan_review", evidence,
                            bool(previous_answer),
                        )
                    personal_fallback = self._limited_personal_plan_fallback(
                        message, evidence, result.tool_trace, locale,
                    )
                    if personal_fallback:
                        return FinnResponsesVerifiedAnswer(
                            "completed", personal_fallback, "limited_personal_plan", evidence,
                            bool(previous_answer),
                        )
                    coach_fallback = (
                        self._emotional_coach_fallback(message, locale)
                        if reason in {
                            "responses_evidence_not_verified",
                            "user_condition_bypass_blocked",
                            "trading_outcome_claim_unverified",
                        } else None
                    )
                    if coach_fallback:
                        return FinnResponsesVerifiedAnswer(
                            "completed", coach_fallback, "safe_emotional_coaching", evidence,
                            bool(previous_answer),
                        )
                    return FinnResponsesVerifiedAnswer(
                        "unavailable",
                        self._fallback_copy(reason, message=message, previous_answer=previous_answer, locale=locale),
                        reason, evidence, bool(previous_answer),
                        rejection_details=rejection_details or None,
                    )
            if static_answer:
                return FinnResponsesVerifiedAnswer(
                    "completed", static_answer, "static_level_geometry", evidence,
                )
            logger.info(
                "FINN Responses answer verification rejected draft: codes=%s available=%s semantic_pass=%s quantities=%s advice=%s technical=%s catalog=%s presentation=%s",
                list(verdict.reason_codes), verdict.available, verdict.passes,
                quantities_supported(result.text), advice_ok, technical_ok,
                catalog_ok, presentation_ok(result.text),
                extra={
                    "stage": "responses_answer_verifier",
                    "reason_codes": list(verdict.reason_codes),
                    "semantic_available": verdict.available,
                    "semantic_passes": verdict.passes,
                    "quantities_supported": quantities_supported(result.text),
                    "advice_supported": advice_ok,
                    "technical_supported": technical_ok,
                    "catalog_focused": catalog_ok,
                    "presentation_ok": presentation_ok(result.text),
                    "evidence_scopes": [item.get("scope") for item in evidence],
                },
            )
        if not result.model_led_coach and limited_evaluation and plan_evaluation and (
            not verdict_passes or not advice_ok or not presentation_ok(result.text)
        ):
            remaining = remaining_lifecycle_seconds()
            if self.client is not None and (remaining is None or remaining > 12):
                def without_internal_ids(value: Any) -> Any:
                    if isinstance(value, dict):
                        return {
                            key: without_internal_ids(item) for key, item in value.items()
                            if key != "id" and not key.endswith("_id") and not key.endswith("_ids")
                        }
                    if isinstance(value, list):
                        return [without_internal_ids(item) for item in value]
                    return value

                focused_scopes = {
                    "read_profile", "read_active_asset", "read_active_setup",
                    "read_linked_strategy", "read_linked_bot", "read_bot_status",
                    "read_indicator_configuration", "read_market_snapshot",
                    "read_macro_snapshot", "read_technical_snapshot", "read_asset_scores",
                }
                focused_evidence = [
                    {
                        "scope": item.get("scope"), "status": item.get("status"),
                        "data": without_internal_ids(item.get("data")),
                        "reason": item.get("reason"),
                    }
                    for item in evidence
                    if item.get("scope") in focused_scopes
                ]
                focused_data = {
                    item["scope"]: item["data"] for item in focused_evidence
                    if item.get("status") == "completed"
                    and item.get("scope") in {"read_profile", "read_active_setup", "read_linked_strategy"}
                    and isinstance(item.get("data"), dict)
                }
                saved_setup = focused_data.get("read_active_setup", {})
                saved_strategy = focused_data.get("read_linked_strategy", {})
                saved_profile = focused_data.get("read_profile", {})
                grounded_plan = {
                    "source": "owner_scoped_persisted_read",
                    "setup": {key: saved_setup.get(key) for key in (
                        "name", "symbol", "timeframe", "setup_type",
                    ) if saved_setup.get(key) is not None},
                    "strategy": {key: saved_strategy.get(key) for key in (
                        "name", "symbol", "timeframe", "entry", "stop_loss",
                        "targets", "entry_type", "level_geometry",
                    ) if saved_strategy.get(key) is not None},
                    "profile_saved": saved_profile.get("has_profile") is True,
                    "component_statuses": {
                        item["scope"]: {
                            "status": item["status"],
                            "reason": item.get("reason"),
                        }
                        for item in focused_evidence
                        if item.get("scope") in {
                            "read_active_setup", "read_linked_strategy", "read_linked_bot",
                        }
                    },
                }
                try:
                    response = await asyncio.wait_for(
                        self.client.responses.create(
                            model="gpt-4o", store=False, tool_choice="none", temperature=0,
                            instructions=(self._model_led_repair_instructions(locale) if result.model_led_coach else (
                                "You are FINN repairing a rejected coaching answer. Write every "
                                "user-facing field in the requested language. The question determines "
                                "response_focus: review, calculation, priorities or general. "
                                "FINN already attempted this evaluation; do not offer to run "
                                "the same unavailable assessment again. "
                                "Use ONLY the typed owner-scoped evidence and the user's own words. "
                                "The grounded_plan is a projection of persisted facts, NOT a "
                                "quality rating. A saved entry, stop and targets are explicitly "
                                "specified levels, not proof of good risk management, attractive "
                                "ratios, plan strength, target feasibility or personal fit. "
                                "A stated rule is not a saved rule unless it appears in saved data. "
                                "The component_statuses are typed results of actual owner-scoped reads. "
                                "If a setup was read but its linked strategy is unavailable, do not "
                                "call that setup a saved strategy or praise its strategy rules. In a "
                                "plan review, identify the missing component as a distinct structural "
                                "limit and make the next check a concrete choice the owner can make, "
                                "rather than only waiting for unavailable market data. A DCA setup "
                                "does not by itself require the user to create a strategy. "
                                "A review must identify a verifiable structural fact, a concrete "
                                "limitation, and one check; having saved levels permits arithmetic "
                                "but does not make a plan good or suitable. A calculation must "
                                "include the exact risk_per_unit and reward_to_risk for each target "
                                "when level_geometry is completed. A priorities answer must give "
                                "the requested number of distinct numbered preparatory steps "
                                "and what to avoid. If live sources are unavailable, make these "
                                "actions preparatory choices based on saved facts or the user's "
                                "own risk constraint, not commands to inspect unavailable data "
                                "right now. Never recommend a trade, modifying saved levels, "
                                "or claim current conditions are met without current evidence. "
                                "Mention unavailable market evidence only as a limit on current "
                                "judgment, not as a substitute for the requested answer. Leave "
                                "Fill the requested structured response_focus. For review, put "
                                "the evidenced structural fact in verified_strength, the actual "
                                "evidence limit in verified_constraint, and one concrete check in "
                                "next_safe_step. For priorities, give distinct preparatory actions "
                                "in priority_actions and an explicit avoid_action. For calculation, "
                                "include absolute risk and every typed ratio in "
                                "conditional_observation. Leave unrelated fields empty. Do not "
                                "turn numeric ratios into praise or trading signals."
                            )),
                            input=json.dumps({
                                "question": message, "locale": locale,
                                "proposed_change_is_not_saved": True,
                                "grounded_plan": grounded_plan,
                                "unavailable_live_scopes": [
                                    item.get("scope") for item in evidence
                                    if item.get("status") != "completed"
                                    and item.get("scope") in {
                                        "read_market_snapshot", "read_macro_snapshot",
                                        "read_technical_snapshot", "read_asset_scores",
                                    }
                                ],
                                "typed_scope_statuses": {
                                    item["scope"]: {"status": item["status"], "reason": item.get("reason")}
                                    for item in focused_evidence
                                    if item.get("status") != "completed"
                                },
                                "rejected_checks": advice_diagnostics.get(result.text, {}).get("rejected_checks", [])
                                + (["assessment_presentation_not_coaching"] if not presentation_ok(result.text) else []),
                            }, ensure_ascii=False, default=str),
                            text=limited_evaluation_format(result.response_focus),
                            max_output_tokens=650,
                        ),
                        timeout=min(8.0, remaining - 3 if remaining is not None else 8.0),
                    )
                    focused = limited_evaluation_answer(
                        str(response.output_text), locale=locale,
                        review_next_step=plan_review_next_step_from_evidence(evidence, locale)
                        if result.response_focus == "review" else None,
                    )
                    focused_verdict, focused_advice, focused_technical, focused_catalog = await asyncio.gather(
                        verify_text(focused), advice_supported(focused),
                        technical_supported(focused), catalog_focused(focused),
                    )
                    if (focused_verdict.available and (focused_verdict.passes or focused_advice)
                            and focused_advice and focused_technical and focused_catalog
                            and quantities_supported(focused) and presentation_ok(focused)):
                        return FinnResponsesVerifiedAnswer(
                            "completed", focused, None, evidence, bool(previous_answer),
                        )
                except Exception as exc:
                    logger.info(
                        "FINN focused evaluation repair unavailable: %s",
                        str(exc) if isinstance(exc, FinnResponsesError) else type(exc).__name__,
                    )
        if not result.model_led_coach and result.response_focus == "priorities" and unavailable_live_for_priorities and not presentation_ok(result.text):
            return limited_fallback()
        if not result.model_led_coach and limited_evaluation and plan_evaluation and (
            result.response_focus == "review"
            or
            review_has_missing_plan_component
            or (result.response_focus == "priorities" and unavailable_live_for_priorities)
        ):
            return limited_fallback()
        if verification_available and (not verdict_passes or not quantities_supported(result.text) or not advice_ok or not technical_ok or not catalog_ok or not presentation_ok(result.text)) and self.client is not None:
            remaining = remaining_lifecycle_seconds()
            if remaining is None or remaining > 8:
                try:
                    repair_model = (
                        os.getenv("FINN_RESPONSES_CLARIFICATION_MODEL", "gpt-6-luna")
                        if result.model_led_coach else "gpt-4o"
                    )
                    response = await asyncio.wait_for(
                        self.client.responses.create(
                            model=repair_model, store=False,
                            **({"reasoning": {"effort": os.getenv("FINN_RESPONSES_REASONING_EFFORT", "none")}}
                               if result.model_led_coach and repair_model.startswith("gpt-6-") else {}),
                            instructions=(self._model_led_repair_instructions(locale) if result.model_led_coach else (
                                "You are FINN. Rewrite every user-facing field entirely in "
                                + ({"nl": "Dutch", "en": "English", "de": "German"}.get(locale or "", "the user's language"))
                                + (". In German, use 'du/dein' consistently, never 'Sie/Ihr'" if locale == "de" else "")
                                + " using ONLY the "
                                "typed evidence, the user's question and any previous verified answer "
                                "for facts. The rejected draft is supplied only to preserve the "
                                "user's actual question and useful reasoning structure: it is NOT "
                                "evidence. Remove or correct every unsupported claim identified by "
                                "the rejection reasons and personal_advice_audit rejected_checks; "
                                "never copy a claim merely because it appears "
                                "in that draft. Do not attach "
                                "a currency or asset unit to a bare numeric field; base_amount=100 does not "
                                "mean 100 BTC, $100 or €100 without explicit currency evidence. "
                                "State unavailable data and unknown causes plainly; "
                                "If read_profile contains a saved risk_profiles value, do not say "
                                "the user's risk profile or risk settings are missing. A saved risk "
                                "style is not a completed suitability assessment. "
                                "A user's description of a plan rule is not proof that it is "
                                "stored in their setup or strategy. Attribute unverified rules "
                                "to the user and reason conditionally; do not claim that a "
                                "saved object requires a trigger absent from typed read evidence. "
                                "For unavailable technical indicators, never suggest a temporary outage "
                                "and check educational facts: RSI below 30 is commonly oversold, not overbought. "
                                "Do not equate overbought or oversold with proof that an asset is "
                                "objectively too expensive or too cheap. "
                                "do not invent prices, user facts, recommendations or provider failures. "
                                "Never print database IDs, even when they appear in evidence. "
                                "Do not replace an explicit action request with a read-only answer; "
                                "without a proposal tool result, do not claim the action was prepared. "
                                "A saved strategy and profile establish their stored values only. "
                                "A 4H chart timeframe is not an investment horizon. Never infer "
                                "that this saved setup favors swing trading or a shorter holding "
                                "period, or recommend a larger chart timeframe for long-term "
                                "investing without explicit supporting evaluation. "
                                + (
                                    "The latest user message answered FINN's preceding question. "
                                    "First acknowledge that exact new user-stated detail in the "
                                    "requested language. Explain what it clarifies and what remains "
                                    "unassessed. Do not present it as already saved, repeat the prior "
                                    "question, or substitute a generic 'leave the setup unchanged' "
                                    "answer for this acknowledgment. "
                                    if result.answer_kind == "answers_previous_question" else ""
                                )
                                + "The proposed change in the user's question is hypothetical, not "
                                "a saved setting. In particular, if saved_state has no amount, "
                                "never call the proposed amount the current DCA amount. "
                                "A completed read_active_setup or read_linked_strategy result means "
                                "those saved fields ARE available; do not say you cannot access them "
                                "or ask the user to repeat them. If the original request asked for a "
                                "plan, distinguish a saved setup from a linked strategy: an unavailable "
                                "read_linked_strategy does not turn the setup into a strategy. "
                                "Specifically, call a saved DCA object a DCA-setup, never a "
                                "DCA-strategy when no linked strategy was found. "
                                "When the user asks whether a proposed change fits, name the verified "
                                "current setting and proposed change, and withhold a suitability judgment "
                                "without an owner-scoped risk evaluation. If the registry evaluation "
                                "returned insufficient_evidence, do not invite the user to confirm or "
                                "implement the proposed change now; state which evidence is missing. "
                                "Do not substitute an unrelated missing field for that choice or "
                                "ask for an amount, frequency or other input already supplied. "
                                "If the original request asked for a "
                                "plan and the chosen setup was resolved, do not repeat the earlier "
                                "setup-choice question. "
                                "If the user asks for one missing indicator, choose at most one "
                                "supported unsaved catalog option with a short general reason; "
                                "never dump the catalog. "
                                "Never say that saved settings fit the user's goals or risk style "
                                "without completed owner-scoped risk and market evidence. For a short "
                                "why follow-up, "
                                "explain the prior verified answer, not why a trading approach might "
                                "be good. If that answer withheld a suitability judgment because "
                                "current evidence was insufficient, explain precisely that limit "
                                "and do not add a claimed benefit of DCA, a positive fit claim, "
                                "historical market conditions or a recommended level change. "
                                + (
                                    "No linked strategy was found in the verified owner-scoped "
                                    "evidence. Refer to the user's stated wait rule as their "
                                    "description, not as a saved strategy. Do not say 'your "
                                    "strategy' or suggest analyzing, following, or changing a "
                                    "strategy the user does not have. Give one concrete process "
                                    "step that needs no strategy or current price. "
                                    if no_linked_strategy_evidence else ""
                                )
                                + (
                                    "The prior answer failed the personal-advice audit. Preserve "
                                    "the answer form requested by the user. Identify verified saved settings; "
                                    + (
                                        "say that FINN attempted the registry evaluation but missing "
                                        "source evidence prevented a suitability conclusion; do not "
                                        "offer the same evaluation again. "
                                        if evaluation_calls else
                                        "say that no current market/risk assessment has been performed, "
                                        "so suitability is not yet established. "
                                    )
                                    + "Do not prescribe levels or suggest that the saved strategy "
                                    "helps achieve an investment goal. Requested preparatory "
                                    "priorities are allowed if each is grounded and none recommends "
                                    "a trade or a change to saved levels. "
                                    if not advice_ok else ""
                                )
                                + (
                                    "FINN already attempted a registry evaluation this turn. Its "
                                    "assessment_status is insufficient_evidence: report the verified "
                                    "saved facts and missing sources, not a completed suitability "
                                    "judgment. Never say that no evaluation was performed and never "
                                    "ask permission to run this same evaluation again without new data. "
                                    "Select response_focus from the actual question: review, calculation, "
                                    "priorities, or general. A review must name a verified structural "
                                    "fact, an evidenced limitation, and a specific check; never label "
                                    "static ratios attractive, good or suitable. A calculation must "
                                    "give risk_per_unit and each reward_to_risk ratio when verified "
                                    "level_geometry exists, then state what remains unknown. A "
                                    "priorities request must keep the requested number of distinct, "
                                    "safe preparatory steps and an avoidance; do not replace it with "
                                    "a generic missing-data warning. saved_context may contain only facts in "
                                    "saved_state, not missing-data explanations. assessment_limit "
                                    "alone names the missing current data, and next_safe_step "
                                    "gives a decision without repeating that reason. "
                                    "Each nonempty field must be a short, complete "
                                    "user-facing sentence; do not return bare names, values, labels, "
                                    "or repeat the user's question. user_proposal is hypothetical and must never "
                                    "be called an existing setting. "
                                    "conditional_observation may reason only from a rule or "
                                    "numbers explicitly supplied by the user or saved evidence; "
                                    "never assert current market conditions or suitability. "
                                    "Each step must be a safe process choice supported by the user's "
                                    "stated plan rule or saved evidence. If the user described a "
                                    "wait or entry rule, explain that it should not be treated as "
                                    "satisfied without checking its conditions. Otherwise keep "
                                    "the saved settings unchanged while evidence is missing. "
                                    "Do not invite execution of a proposed change. "
                                    if limited_evaluation and plan_evaluation else ""
                                )
                                + (
                                    "This is a portfolio evaluation with incomplete profile evidence, "
                                    "not a plan or strategy review. Use read_portfolio as the source "
                                    "for balances, exposure and Paper-bot settings. Distinguish a "
                                    "budget limit from available cash, and Paper-bot configuration "
                                    "from a live position. Give one brief paragraph in natural "
                                    "language, no headings or field inventory. State what the "
                                    "portfolio currently shows and that personal suitability is "
                                    "unknown without a saved risk profile. Do not suggest investing "
                                    "or imply that zero invested value is itself a risk."
                                    if limited_evaluation and not plan_evaluation and any(
                                        call["result"].get("evaluation_operation_id") == "evaluate_portfolio"
                                        for call in evaluation_calls
                                    ) else ""
                                )
                                + (
                                    "The current question proposes a concrete amount. Preserve its "
                                    "exact amount in the answer as a hypothetical proposal, clearly "
                                    "separate from saved settings. Do not omit it or call it saved. "
                                    if evaluation_calls and self._currency_amounts(message)
                                    and not self._currency_amounts(message) <= self._currency_amounts(result.text)
                                    else ""
                                )
                                + (
                                    "The user proposed this amount, not FINN. Attribute the "
                                    "hypothetical change to the user (you/je/du), never write "
                                    "'I am considering' or its first-person translation. "
                                    if not self._proposal_speaker_is_user(result.text) else ""
                                )
                                + (
                                    "Do not speak as if FINN itself wants to add, create, update "
                                    "or delete the user's data. Answer the user's question as an "
                                    "assistant; a read question does not authorize a mutation. "
                                    if not self._assistant_does_not_claim_user_mutation(result.text) else ""
                                )
                                + (
                                    "The prior answer was a backend inventory, not coaching. Write "
                                    "one short paragraph with conclusion, evidence-based reason, "
                                    "one relevant next step and any limitation. No headings, bullets, "
                                    "profile-field list or unsolicited indicator suggestion. "
                                    if not presentation_ok(result.text) else ""
                                )
                                + (
                                    "The user asks what help FINN can offer based on saved profile facts. "
                                    "Describe one or two kinds of assistance, such as explaining a saved "
                                    "plan or checking its evidence. Do not recommend a strategy, investment, "
                                    "trade or suitability conclusion. Do not say a method is secure, "
                                    "conservative, aligned with this user's preferences, or likely to "
                                    "grow their wealth. Do not imply an assessment was done. "
                                    if profile_only else ""
                                )
                                + (
                                    "The user asked why, but the draft repeated the previous answer. "
                                    "Explain the specific evidence limit in one or two fresh sentences. "
                                    "Do not restate the saved setup, risk style, or prior conclusion. "
                                    if not self._followup_advances_conversation(
                                        message, previous_answer, result.text,
                                    ) else ""
                                )
                                + (
                                    "The latest question asks what decision to make next. Identify "
                                    "one concrete preparatory choice grounded in the previous "
                                    "verified answer, not another explanation of why suitability "
                                    "is unknown. The choice must be within the user's control; "
                                    "do not tell them to decide about unavailable source data. "
                                    "Do not introduce a named indicator, asset or catalog option "
                                    "that the immediately previous verified answer did not mention. "
                                    "If no trade choice is supported, offer the process choice of "
                                    "leaving the current saved setup unchanged while the required "
                                    "evidence is unavailable. Do not recommend a trade without "
                                    "current evidence. "
                                    if previous_answer and (
                                        not advice_ok or (
                                            reusing_previous_read
                                            and self._introduces_new_catalog_option(
                                                result.text, previous_answer,
                                                tuple((*evidence, *relevant_previous_source_evidence)),
                                            )
                                        )
                                    ) else ""
                                )
                                + (
                                    "FINN already attempted this evaluation and found required "
                                    "sources unavailable. Do not ask whether to run the same "
                                    "evaluation again. Explain the limitation and give one "
                                    "feasible next user decision instead. "
                                    if evaluation_calls and self._reoffers_attempted_evaluation(result.text)
                                    else ""
                                )
                                + (
                                    "This is a next-decision follow-up, not a fresh suitability "
                                    "assessment. Answer the question with one safe process choice "
                                    "grounded in the verified prior answer: leave the saved setup "
                                    "unchanged until a current assessment is possible. State this "
                                    "as a decision the user can make, not as an invitation to "
                                    "confirm, execute, or change a trading action. Do not repeat "
                                    "only why the assessment is unavailable. Do not infer why a "
                                    "source is unavailable. "
                                    if result.answer_kind == "grounded_next_decision" else ""
                                )
                                + (
                                    "The rejected draft promised an outcome not established by FINN evidence. "
                                    "Write a short process explanation instead: separate the user's own rule "
                                    "from today's unknown market conditions, avoid all claims of reduced loss "
                                    "or improved success, and ask at most one concrete clarifying question. "
                                    if self._promises_unverified_trading_outcome(result.text) else ""
                                )
                                + "If the user describes a decision rule and asks whether to bypass it, "
                                "answer that process question first: treat the rule as user-stated, "
                                "not saved evidence; do not treat its trigger as met without checking. "
                                "Explain the trade-off without claiming that waiting increases success, "
                                "improves entries, or reduces losses unless typed evidence proves it. "
                                "For any question asking for a choice, give concrete safe "
                                "process decision grounded in user-stated conditions or verified "
                                "evidence; if the user asked for multiple priorities, preserve "
                                "that number. 'It is your choice' is not an answer. "
                                "Mention missing live data only as the limit on assessing today's "
                                "conditions, not as a substitute for the decision. Do not lead with "
                                "an inventory of saved setup fields. "
                                "Keep it brief and natural. Never expose internal IDs or reason codes."
                            )),
                            input=json.dumps({
                                "question": message,
                                **({"rejected_draft_not_evidence": result.text}
                                   if not result.model_led_coach
                                   and quantities_supported(result.text) and technical_ok else {}),
                                "saved_state": [
                                    item.get("data") for item in compact
                                    if item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                                    and item.get("status") == "completed"
                                ],
                                "proposed_change_is_not_saved": True,
                                "previous_verified_answer": previous_answer or None,
                                "antecedent_verified_answer": antecedent_answer or None,
                                "evidence": compact,
                                "registered_operations": summary["registered_operations"],
                                "typed_unavailable_reasons": summary["typed_unavailable_reasons"],
                                "rejection_reasons": list(verdict.reason_codes)
                                + (["saved_entity_type_not_supported"] if not self._saved_entity_type_supported(
                                    result.text,
                                    tuple((*evidence, *(relevant_previous_source_evidence if reusing_previous_read else ()))),
                                    user_message=message,
                                ) else [])
                                + (["saved_horizon_not_supported"] if not self._saved_horizon_claim_supported(
                                    result.text, tuple((*evidence, *relevant_previous_source_evidence)),
                                ) else [])
                                + (["currency_unit_not_supported"] if not self._currency_units_supported(
                                    answer=result.text, message=message, previous_answer=previous_answer,
                                    evidence=evidence,
                                ) else [])
                                + (["quantity_claim_not_supported"] if not quantities_supported(result.text) else [])
                                + (["personal_advice_not_grounded"] if not advice_ok else [])
                                + (["technical_claim_not_grounded"] if not technical_ok else [])
                                + (["catalog_answer_not_focused"] if not catalog_ok else [])
                                + (["assessment_presentation_not_coaching"] if not presentation_ok(result.text) else [])
                                + (["unverified_outcome_claim"] if self._promises_unverified_trading_outcome(result.text) else []),
                                "rejected_claim_quotes": list(getattr(verdict, "rejected_claim_quotes", []) or []),
                                "personal_advice_audit": advice_diagnostics.get(result.text, {}),
                            }, ensure_ascii=False, default=str),
                            tool_choice="none",
                            **({"text": limited_evaluation_format()}
                               if limited_evaluation and plan_evaluation and not result.model_led_coach else {}),
                        ),
                        timeout=min(8.0, remaining - 3 if remaining is not None else 8.0),
                    )
                    revised = str(getattr(response, "output_text", "") or "").strip()
                    if not revised:
                        revised = "\n".join(
                            str(getattr(part, "text", "") or "")
                            for item in (getattr(response, "output", None) or [])
                            if getattr(item, "type", None) == "message"
                            for part in (getattr(item, "content", None) or [])
                            if getattr(part, "type", None) == "output_text"
                        ).strip()
                    if revised and limited_evaluation and plan_evaluation and not result.model_led_coach:
                        revised = limited_evaluation_answer(
                            revised, locale=locale,
                            review_next_step=plan_review_next_step_from_evidence(evidence, locale)
                            if result.response_focus == "review" else None,
                        )
                    if revised:
                        (revised_verdict, revised_advice_ok, revised_technical_ok,
                         revised_catalog_ok) = await asyncio.gather(
                            verify_text(revised),
                            advice_supported(revised),
                            technical_supported(revised),
                            catalog_focused(revised),
                        )
                        revised_passes = revised_verdict.passes if result.model_led_coach else (
                            revised_verdict.passes or (
                                not previous_explanation_only and personal_evidence
                                and self.client is not None and revised_advice_ok
                            )
                        )
                        revised_available = revised_verdict.available if result.model_led_coach else (
                            revised_verdict.available or (
                                independently_audited_limit and revised_advice_ok
                            )
                        )
                        if not (revised_available and revised_passes and revised_advice_ok
                                and revised_technical_ok and revised_catalog_ok
                                and quantities_supported(revised) and presentation_ok(revised)):
                            logger.info(
                                "FINN Responses answer repair rejected: codes=%s semantic_pass=%s advice=%s technical=%s catalog=%s quantities=%s presentation=%s",
                                list(revised_verdict.reason_codes), revised_verdict.passes,
                                revised_advice_ok, revised_technical_ok, revised_catalog_ok,
                                quantities_supported(revised), presentation_ok(revised),
                            )
                        if revised_available and revised_passes and quantities_supported(revised):
                            if not revised_advice_ok or not revised_technical_ok or not revised_catalog_ok or not presentation_ok(revised):
                                if limited_evaluation:
                                    return limited_fallback()
                                if result.answer_kind == "answers_previous_question" and previous_answer:
                                    return FinnResponsesVerifiedAnswer(
                                        "completed", self._user_detail_acknowledgement(message, locale),
                                        "user_detail_acknowledged", evidence, True,
                                    )
                                safe_decision = await typed_next_decision_fallback()
                                if safe_decision is not None:
                                    return safe_decision
                                profile_question = missing_profile_clarification()
                                if profile_question is not None:
                                    return profile_question
                                safe_explanation = prior_evaluation_explanation()
                                if safe_explanation is not None:
                                    return safe_explanation
                                return FinnResponsesVerifiedAnswer(
                                    "unavailable",
                                    self._fallback_copy(claim_failure_reason() or "responses_evidence_not_verified", message=message, previous_answer=previous_answer, locale=locale),
                                    claim_failure_reason() or "responses_evidence_not_verified", evidence, bool(previous_answer),
                                )
                            return FinnResponsesVerifiedAnswer(
                                "completed", revised, None, evidence, bool(previous_answer),
                            )
                except Exception:
                    pass
        if not verification_available or not verdict_passes or not quantities_supported(result.text) or not advice_ok or not technical_ok or not catalog_ok or not presentation_ok(result.text):
            if limited_evaluation:
                return limited_fallback()
            safe_explanation = prior_evaluation_explanation()
            if safe_explanation is not None:
                return safe_explanation
            if previous_explanation_only and previous_answer and (
                unavailable_without_cause
                or (not previous_clarification_reason and any(
                    item.get("reason") == "source_unavailable" for item in previous_source_evidence
                ))
            ):
                return FinnResponsesVerifiedAnswer(
                    "unavailable",
                    self._fallback_copy(
                        "previous_source_unavailable", message=message,
                        previous_answer=previous_answer, locale=locale,
                    ),
                    "source_unavailable", evidence, True,
                )
            if result.answer_kind == "answers_previous_question" and previous_answer:
                return FinnResponsesVerifiedAnswer(
                    "completed", self._user_detail_acknowledgement(message, locale),
                    "user_detail_acknowledged", evidence, True,
                )
            safe_decision = await typed_next_decision_fallback()
            if safe_decision is not None:
                return safe_decision
            profile_question = missing_profile_clarification()
            if profile_question is not None:
                return profile_question
            reason = claim_failure_reason() or (
                "responses_evidence_not_verified"
                if not quantities_supported(result.text)
                else self._typed_failure_reason((*evidence, *relevant_previous_source_evidence))
            )
            answer = self._fallback_copy(
                "previous_source_unavailable"
                if previous_answer and "unsupported_cause" in verdict.reason_codes
                else reason,
                message=message, previous_answer=previous_answer, locale=locale,
            )
            return FinnResponsesVerifiedAnswer(
                "unavailable", answer, reason, evidence, bool(previous_answer),
            )
        final_text = (
            self._attribute_user_proposal(answer=result.text, message=message, locale=locale)
            if result.model_led_coach and result.answer_kind == "free_text"
            and not any((call.get("result") or {}).get("proposal_id") for call in result.tool_trace)
            else result.text
        )
        if _hypothetical_trade_reflection(message) and not re.search(
            r"\b(?:voorbeeld|stel|hypothetisch|example|suppose|hypothetical|Beispiel|angenommen)\b",
            final_text, re.I,
        ):
            lead = {
                "nl": "In je hypothetische voorbeeld:",
                "en": "In your hypothetical example:",
                "de": "In deinem hypothetischen Beispiel:",
            }[locale if locale in {"nl", "en", "de"} else "nl"]
            final_text = f"{lead}\n\n{final_text}"
        return FinnResponsesVerifiedAnswer("completed", final_text, None, evidence, bool(previous_answer))
