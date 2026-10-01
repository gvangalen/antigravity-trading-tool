"""Model-driven FINN entrypoint before the existing action safety pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import logging
import os
import re
from time import monotonic
from typing import Any, Mapping

from backend.services.asset_catalog_service import (
    DEFAULT_ASSET_CATALOG, mentioned_catalog_symbols, resolve_catalog_symbol,
)
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_responses_loop import (
    FinnResponsesError, FinnResponsesLoop, FinnResponsesResult,
    _hypothetical_trade_reflection, _read_only_stop_loss_coaching,
    _saved_confirmation_readback,
)
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolError
from backend.services.finn_v2_responses_tool_relevance import FinnResponsesToolRelevanceGuard
from backend.services.finn_v2_verified_turn_context import project_verified_turn
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from backend.services import finn_v2_entity_resolution_service as entity_resolution_module
from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService
from backend.services.finn_v2_operation_classification_service import FinnV2OperationClassificationService

logger = logging.getLogger(__name__)


def _listed_setup_ordinal(message: str) -> int | None:
    """Resolve an ordinal only against a previously verified ordered inventory."""
    match = re.search(
        r"\b(?:de|het|nummer|nr\.?|the|das|die)\s+"
        r"(eerste|tweede|derde|vierde|vijfde|zesde|zevende|achtste|negende|tiende|"
        r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        r"erste|zweite|dritte|vierte|fünfte|sechste|siebte|achte|neunte|zehnte|"
        r"[1-9][0-9]?(?:e|de|ste|st|nd|rd|th)?)\b",
        message, re.I,
    )
    if not match:
        return None
    token = match.group(1).casefold()
    names = (
        "eerste tweede derde vierde vijfde zesde zevende achtste negende tiende "
        "first second third fourth fifth sixth seventh eighth ninth tenth "
        "erste zweite dritte vierte fünfte sechste siebte achte neunte zehnte"
    ).split()
    if token in names:
        return names.index(token) % 10
    number = re.match(r"\d+", token)
    return int(number.group()) - 1 if number else None


def _explicit_rule_transfer_assets(message: str) -> tuple[str, str] | None:
    """Extract the source of a named rule and the other named target asset."""
    assets = mentioned_catalog_symbols(message)
    if len(assets) != 2 or not re.search(
        r"\b(?:geldt|toepass\w*|gebruik\w*|overnem\w*|apply|use|applies|gilt|anwenden)\b",
        message, re.I,
    ):
        return None
    for match in re.finditer(r"\b(?:dca[- ]?)?(?:regel|rule|plan|setup)s?\b", message, re.I):
        prefix = message[max(0, match.start() - 35):match.start()]
        nearby = []
        for symbol in assets:
            catalog = DEFAULT_ASSET_CATALOG[symbol]
            names = (symbol, catalog.get("display_name"), *(catalog.get("aliases") or ()))
            for name in names:
                if name:
                    nearby.extend(
                        (found.end(), symbol)
                        for found in re.finditer(
                            rf"(?<![a-z0-9]){re.escape(str(name))}(?![a-z0-9])", prefix, re.I,
                        )
                    )
        if nearby and len(prefix) - max(nearby)[0] <= 15:
            source = max(nearby)[1]
            return source, next(iter(assets - {source}))
    return None


def _verified_listed_setup_reference(previous_response: Mapping[str, Any] | None) -> tuple[int, int] | None:
    """Return the last selected (ordinal, owner-scoped ID) from a verified list turn."""
    if (previous_response or {}).get("terminal_kind") != "listed_setup_reference":
        return None
    for call in reversed((previous_response or {}).get("tool_trace") or []):
        if call.get("name") != "get_saved_setup_inventory" or call.get("status") != "completed":
            continue
        arguments = call.get("arguments") or {}
        ordinal = arguments.get("listed_ordinal")
        setup_ids = arguments.get("setup_ids")
        if not isinstance(ordinal, int) or ordinal < 1 or not isinstance(setup_ids, list) or len(setup_ids) != 1:
            continue
        setup_id = setup_ids[0]
        if not isinstance(setup_id, int) or setup_id < 1:
            continue
        if any(
            item.get("scope") == "read_saved_setup_inventory"
            and item.get("status") == "completed"
            and any(
                isinstance(row, dict) and row.get("setup_id") == setup_id
                for row in (item.get("data") or {}).get("setups") or []
            )
            for item in (call.get("result") or {}).get("results") or []
        ):
            return ordinal, setup_id
    return None


@dataclass(frozen=True)
class FinnResponsesFrontDoorResult:
    response: FinnResponsesResult
    proposal_analysis: RequestAnalysisResult | None
    previous_response: dict[str, Any] | None = None
    recent_action_result: dict[str, Any] | None = None
    locale: str = "nl"


class FinnResponsesFrontDoor:
    @staticmethod
    def _model_led_instructions(locale: str) -> str:
        language = {"nl": "Dutch", "en": "English", "de": "German"}.get(locale, "Dutch")
        return (
            "You are FINN, a personal trading coach. Respond entirely in " + language + ". "
            "This is the effective reply language from the owner's preference and any explicit "
            "language switch. The latest user message or a tool result may be in another language; "
            "do not mirror that language unless the user explicitly requests a switch. "
            "Lead the conversation: answer directly when general reasoning suffices, ask one "
            "useful follow-up when a choice is missing, and call one or more FINN tools when "
            "the answer needs saved account facts, a personal assessment, or current data. "
            "For a general explanation, answer without account reads and do not invent an "
            "example price, currency amount, or holding. If asked what to do now, offer a "
            "specific safe process step rather than a generic invitation to ask again. "
            "User statements are conversational context, not proof of saved FINN facts. "
            "A short reply to a question you just asked supplies conversational detail; it "
            "does not authorize changing a saved object unless the user explicitly requests that change. "
            "Treat each tool's status, availability, source, as_of and evidence_boundary or "
            "assessment_boundary as authoritative. A partial or insufficient assessment "
            "supports only the returned facts and limits, never personal suitability. "
            "A chart timeframe is not a holding horizon. Do not invent a saved object, "
            "market reading, trading outcomes, or cause of unavailable data. A typed object "
            "not-resolved result means no unique owner-scoped object, not a provider outage. "
            "Keep user-stated entry conditions intact; do not suggest any position before "
            "a required condition is met, including a smaller position. "
            "For a requested mutation, choose the registry-backed proposal tool. FINN validates "
            "inputs and dependencies; only explicit user confirmation can execute it. "
            "Never claim a write happened before confirmed execution, and never suggest a "
            "broker order or live-bot activation. Hide internal IDs and error codes."
        )

    def __init__(self, *, client: Any, session: Any = None, session_factory: Any = None, user_id: int, run_id: str, model_led_coach: bool = True) -> None:
        self.client = client
        self.user_id = user_id
        self.run_id = run_id
        self.model_led_coach = model_led_coach
        self.reads = FinnResponsesReadExecutor(
            session=session, session_factory=session_factory, user_id=user_id, run_id=run_id,
        )
        self.proposals = FinnResponsesProposalSelection()
        self.relevance_guard = FinnResponsesToolRelevanceGuard(client)

    @staticmethod
    def binds_guided_slot(*, message: str, contract: Any, registry: Any, requested_slot: str) -> bool:
        """A short typed answer belongs to the persisted slot, not a new model intent."""
        states = FinnV2OperationStateService()
        normalized = message.strip().casefold()
        if not normalized or "?" in message or states.is_cancel_intent(message):
            return False
        if any(
            normalized.startswith(alias.casefold())
            for other in registry.list()
            if other.operation_id != contract.operation_id
            for alias in other.aliases
        ):
            return False
        return (
            states._requested_slot_value(field=requested_slot, text=message, contract=contract) is not None
            and states._is_short_slot_answer(message, requested_slot=requested_slot)
        )

    async def run(
        self,
        *,
        message: str,
        instructions: str,
        conversation_context: Mapping[str, object],
        verified_asset: str | None,
        previous_response_id: str | None = None,
        previous_response: dict[str, Any] | None = None,
        prior_tool_trace: tuple[dict[str, Any], ...] = (),
        model_message: str | None = None,
        resuming_clarification: bool = False,
        corrected_guided_operation_id: str | None = None,
        locale: str = "nl",
        force_read_repair: bool = False,
        rejection_feedback: dict[str, Any] | None = None,
    ) -> FinnResponsesFrontDoorResult:
        selected: RequestAnalysisResult | None = None
        individual_proposals = (
            os.getenv("APP_ENV") == "local_finn"
            and os.getenv("FINN_PER_OPERATION_TOOLS_EXPERIMENT") == "1"
        )
        catalog = FinnResponsesToolCatalog(individual_proposals=individual_proposals)
        if corrected_guided_operation_id:
            contract = self.proposals.registry.require_supported(corrected_guided_operation_id)
            if contract.mode not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
                raise ValueError("guided_target_correction_requires_action_contract")
            selected = self.proposals.from_call(
                call=FinnResponsesToolCall(
                    name=catalog.proposal_tool_for_operation(contract.operation_id),
                    operation_id=contract.operation_id, inputs={}, read_tools=(),
                    required_inputs=contract.required_inputs, missing_inputs=(), draft_intent="new",
                ),
                message=message, conversation_context=conversation_context,
                verified_asset=verified_asset,
            )
            return FinnResponsesFrontDoorResult(
                FinnResponsesResult(
                    text="Het gecorrigeerde doel wordt als nieuw voorstel beoordeeld.",
                    response_id=f"guided-correction-{self.run_id}",
                    tool_trace=({
                        "name": "guided_target_correction", "status": "completed",
                        "result": {"operation_id": contract.operation_id, "domain": contract.domain},
                    },),
                    response_id_reusable=False,
                ),
                selected, previous_response, locale=locale,
            )
        read_context: list[dict[str, Any]] = []
        completed_read_calls: set[tuple[str, str]] = set()
        pending_operation = FinnV2OperationStateService.pending_operation_id(conversation_context)
        guided_state = dict(conversation_context.get("active_guided_operation") or {})
        requested_slot = str(guided_state.get("next_missing_input") or "")
        if pending_operation and requested_slot and not FinnV2OperationStateService.is_cancel_intent(message):
            contract = self.proposals.registry.require_supported(pending_operation)
            states = self.proposals.states
            switches_operation = any(
                message.strip().casefold().startswith(alias.casefold())
                for other in self.proposals.registry.list()
                if other.operation_id != pending_operation
                for alias in other.aliases
            )
            if self.binds_guided_slot(
                message=message, contract=contract, registry=self.proposals.registry,
                requested_slot=requested_slot,
            ) or (states._is_explicit_correction(message) and not switches_operation and "?" not in message):
                selected = self.proposals.from_call(
                    call=FinnResponsesToolCall(
                        name=catalog.proposal_tool_for_operation(pending_operation),
                        operation_id=pending_operation, inputs={}, read_tools=(),
                        required_inputs=contract.required_inputs,
                        missing_inputs=tuple(guided_state.get("missing_required_inputs") or ()),
                        draft_intent="new",
                    ),
                    message=message, conversation_context=conversation_context,
                    verified_asset=verified_asset,
                )
                return FinnResponsesFrontDoorResult(
                    FinnResponsesResult(
                        text="Het concept is bijgewerkt.",
                        response_id=previous_response_id or f"guided-{self.run_id}",
                        tool_trace=({
                            "name": "guided_slot_binding", "status": "completed",
                            "result": {"operation_id": pending_operation, "requested_slot": requested_slot},
                        },),
                        response_id_reusable=False,
                    ),
                    selected, previous_response, locale=locale,
                )
        guard = getattr(self, "relevance_guard", None)
        previous_kind = str((previous_response or {}).get("terminal_kind") or "")
        request_facts = FinnV2RequestPreprocessorService().preprocess(message=message)
        is_read_request = request_facts.action_polarity == "read"
        mentioned_assets = mentioned_catalog_symbols(message)
        prior_inventory = next((
            call for call in reversed((previous_response or {}).get("tool_trace") or [])
            if call.get("name") == "get_saved_setup_inventory"
            and not (call.get("arguments") or {}).get("listed_ordinal")
            and call.get("status") == "completed"
            and any(
                item.get("scope") == "read_saved_setup_inventory"
                and item.get("status") == "completed"
                for item in (call.get("result") or {}).get("results") or []
            )
        ), None)
        prior_inventory_data = next((
            item.get("data") for item in (prior_inventory or {}).get("result", {}).get("results") or []
            if item.get("scope") == "read_saved_setup_inventory"
            and isinstance(item.get("data"), dict)
        ), {})
        prior_setup_ids = [
            row["setup_id"] for row in prior_inventory_data.get("setups") or []
            if isinstance(row, dict) and isinstance(row.get("setup_id"), int)
        ]
        # A request to justify the last selected list item still refers to
        # that owner-scoped item. Re-read its verified ID instead of relying
        # on the old prose answer or asking the model to infer an identity.
        prior_selected = _verified_listed_setup_reference(previous_response)
        asks_for_evidence = is_read_request and request_facts.discourse_act == "evidence_follow_up"
        evidence_followup = asks_for_evidence and prior_selected is not None
        listed_ordinal = _listed_setup_ordinal(message) if prior_setup_ids else None
        if listed_ordinal is None and evidence_followup:
            listed_ordinal = prior_selected[0] - 1
        listed_setup_id = (
            prior_setup_ids[listed_ordinal]
            if listed_ordinal is not None and 0 <= listed_ordinal < len(prior_setup_ids)
            else prior_selected[1] if evidence_followup
            else None
        )
        # An ordinal and an evidence request can arrive in the same message.
        # The verified inventory already supplies the identity in that case.
        evidence_followup = asks_for_evidence and listed_setup_id is not None
        if (is_read_request and pending_operation is None and not resuming_clarification
                and listed_ordinal is not None and listed_setup_id is None):
            return FinnResponsesFrontDoorResult(
                FinnResponsesResult(
                    text="Referenced list position is outside the verified inventory.",
                    response_id=f"local-setup-reference-out-of-range-{self.run_id}",
                    tool_trace=(), answer_kind="listed_setup_reference_out_of_range",
                    model_led_coach=True, response_id_reusable=False,
                ), selected, previous_response, locale=locale,
            )
        prior_inventory_asset = resolve_catalog_symbol(
            (prior_inventory or {}).get("arguments", {}).get("asset")
        )
        prior_inventory_timeframe = str(
            (prior_inventory or {}).get("arguments", {}).get("timeframe") or ""
        ).upper()
        collection_cue = bool(re.search(
            r"\b(?:setups|set-ups|plannen|plans|(?:alle|all)\s+(?:mijn|my)?\s*setups?)\b",
            message, re.I,
        ))
        explicit_rule_transfer = _explicit_rule_transfer_assets(message)
        cross_asset_cue = len(mentioned_assets) >= 2 and bool(re.search(
            r"\b(?:dca|plans?|plannen?|setups?|regels?|rules?)\b", message, re.I,
        ))
        inventory_followup = (
            bool(prior_setup_ids) and previous_kind != "cross_asset_rule_scope"
        ) and bool(re.search(
            r"\b(?:die|deze|daarvan|welke|welk|bij|entry\w*|instap\w*|"
            r"bevestig\w*|those|which|any)\b", message, re.I,
        ))
        confirmation_followup = inventory_followup and bool(re.search(
            r"\b(?:entry\w*|instap\w*|bevestig\w*|confirmation|trigger\w*)\b",
            message, re.I,
        ))
        confirmation_subject = bool(re.search(
            r"\b(?:entry\w*|instap\w*|bevestig\w*|confirmation|trigger\w*)\b",
            message, re.I,
        ))
        explicit_list = collection_cue and bool(
            re.search(r"\b(?:noem|opsom\w*|lijst|list|alle|all|namen|names|overzicht|show|toon)\b", message, re.I)
            or re.search(r"\b(?:welke|which)\b.{0,80}\b(?:staan|heb|have|are)\b", message, re.I)
        )
        query: dict[str, str] | None = None
        if is_read_request and explicit_rule_transfer:
            query = {"kind": "cross_asset_scope", "source_asset": explicit_rule_transfer[0],
                     "target_asset": explicit_rule_transfer[1]}
        elif is_read_request and listed_setup_id and not mentioned_assets:
            query = {"kind": "listed_setup_reference"}
        elif is_read_request and not cross_asset_cue and explicit_list:
            query = {"kind": "confirmation_inventory" if confirmation_subject else "inventory"}
        elif is_read_request and confirmation_followup and not mentioned_assets:
            query = {"kind": "confirmation_inventory"}
        if (
            pending_operation is None and not resuming_clarification and is_read_request
            and (collection_cue or cross_asset_cue or inventory_followup or listed_setup_id)
            and query is None
            and guard is not None
            and callable(getattr(guard, "saved_plan_query_kind", None))
        ):
            query = await guard.saved_plan_query_kind(
                message=message, previous_kind=previous_kind,
                previous_answer=str((previous_response or {}).get("answer") or ""),
            )
        # The classifier is a semantic router. These narrow fallbacks keep an
        # unambiguous read available if the selector provider is unavailable.
        if query is None and is_read_request:
            if FinnV2OperationClassificationService._is_explicit_setup_collection_read(message):
                query = {"kind": "inventory"}
            elif _saved_confirmation_readback(message):
                query = {"kind": "confirmation_inventory"}
        query_kind = str((query or {}).get("kind") or "none")
        source_asset = str((query or {}).get("source_asset") or "").upper()
        target_asset = str((query or {}).get("target_asset") or "").upper()
        if query_kind == "cross_asset_scope" and not (
            source_asset != target_asset and {source_asset, target_asset} <= mentioned_assets
        ):
            query_kind = "none"
        if (
            pending_operation is None
            and not resuming_clarification
            and is_read_request
            and query_kind in {"inventory", "confirmation_inventory", "cross_asset_scope", "listed_setup_reference"}
        ):
            # Collection questions have their own typed, owner-scoped read.
            # No active setup or linked strategy is selected here.
            inputs = (
                {"asset": next(iter(mentioned_assets))}
                if query_kind != "cross_asset_scope" and len(mentioned_assets) == 1
                and not entity_resolution_module.FinnV2EntityResolutionService.is_all_assets_collection_request(message)
                else {}
            )
            timeframe = re.search(r"\b(?:15m|30m|1h|4h|1d|1w)\b", message, re.I)
            if timeframe and query_kind != "cross_asset_scope":
                inputs["timeframe"] = timeframe.group().upper()
            if query_kind == "listed_setup_reference":
                inputs = {
                    **({"asset": prior_inventory_asset} if prior_inventory_asset else {}),
                    "setup_ids": [listed_setup_id],
                }
            elif query_kind != "cross_asset_scope" and inventory_followup and not mentioned_assets:
                inputs = {
                    **({"asset": prior_inventory_asset} if prior_inventory_asset else {}),
                    **({"timeframe": prior_inventory_timeframe} if prior_inventory_timeframe and not timeframe else {}),
                    **({"timeframe": timeframe.group().upper()} if timeframe else {}),
                    "setup_ids": prior_setup_ids,
                }
            collection_call = FinnResponsesToolCall(
                name="get_saved_setup_inventory", operation_id=None,
                inputs=inputs, read_tools=("read_saved_setup_inventory",),
                required_inputs=(), missing_inputs=(),
            )
            try:
                collection_read = await self.reads(collection_call)
            except Exception:
                logger.warning("FINN owner-scoped setup collection pre-read failed", exc_info=True)
                collection_read = {}
            collection_evidence = next((
                item for item in collection_read.get("results", [])
                if item.get("scope") == "read_saved_setup_inventory"
                and item.get("status") == "completed"
                and isinstance(item.get("data"), dict)
                and isinstance(item["data"].get("setups"), list)
            ), None)
            if collection_evidence is not None:
                return FinnResponsesFrontDoorResult(
                    FinnResponsesResult(
                        text="Verified saved setup context.",
                        response_id=f"local-setup-collection-{self.run_id}",
                        tool_trace=({
                            "name": collection_call.name, "status": collection_read["status"],
                            "arguments": {
                                **collection_call.inputs,
                                **({"listed_ordinal": listed_ordinal + 1}
                                   if query_kind == "listed_setup_reference" else {}),
                                **({"evidence_followup": True} if evidence_followup else {}),
                                **({"source_asset": source_asset, "target_asset": target_asset}
                                   if query_kind == "cross_asset_scope" else {}),
                            },
                            "result": collection_read,
                        },),
                        answer_kind=("listed_setup_reference" if query_kind == "listed_setup_reference"
                                     else "cross_asset_rule_scope" if query_kind == "cross_asset_scope"
                                     else "saved_confirmation_inventory" if query_kind == "confirmation_inventory"
                                     else "saved_setup_collection"),
                        model_led_coach=True,
                        response_id_reusable=False,
                    ),
                    selected, previous_response, locale=locale,
                )
            return FinnResponsesFrontDoorResult(
                FinnResponsesResult(
                    text="Saved setup inventory unavailable.",
                    response_id=f"local-setup-inventory-unavailable-{self.run_id}",
                    tool_trace=({
                        "name": collection_call.name,
                        "status": str(collection_read.get("status") or "unavailable"),
                        "arguments": {
                            **collection_call.inputs,
                            **({"listed_ordinal": listed_ordinal + 1}
                               if query_kind == "listed_setup_reference" else {}),
                            **({"evidence_followup": True} if evidence_followup else {}),
                            **({"source_asset": source_asset, "target_asset": target_asset}
                               if query_kind == "cross_asset_scope" else {}),
                        },
                        "result": collection_read,
                    },),
                    answer_kind=("cross_asset_inventory_unavailable"
                                 if query_kind == "cross_asset_scope" else "saved_inventory_unavailable"),
                    model_led_coach=True,
                    response_id_reusable=False,
                ), selected, previous_response, locale=locale,
            )
        target_retry_used = False
        relevance_retry_used = False
        recommended_read_operation: str | None = None
        previous_answer_only = False
        next_decision_from_previous = False
        conditional_next_step_from_previous = False
        answering_previous_question = False
        resolved_detail_clarification = False
        pending_clarification = dict(conversation_context.get("responses_clarification") or {})
        detail_clarification = (
            resuming_clarification
            and pending_clarification.get("reason") == "user_detail_required"
        )
        if (
            guard is not None
            and previous_response and previous_response.get("answer") and not pending_operation
            and not force_read_repair
            and not _read_only_stop_loss_coaching(message)
            and not _hypothetical_trade_reflection(message)
            and (not resuming_clarification or detail_clarification)
            and (
                not getattr(self, "model_led_coach", False)
                or previous_response.get("terminal_status") in {None, "completed"}
            )
        ):
            classification_started = monotonic()
            sufficiency = await guard.previous_answer_suffices(
                message=message,
                previous_answer=str(previous_response.get("answer") or ""),
                **({
                    "model": os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
                    "reasoning_effort": os.getenv("FINN_RESPONSES_REASONING_EFFORT", "none"),
                } if getattr(self, "model_led_coach", False) else {}),
            )
            if getattr(self, "model_led_coach", False) and sufficiency not in {
                "explain_previous", "next_decision_from_previous",
                "conditional_next_step_from_previous",
            }:
                sufficiency = False
            previous_answer_only = sufficiency in {
                "explain_previous", "next_decision_from_previous",
                "conditional_next_step_from_previous",
                "answers_previous_question",
            }
            next_decision_from_previous = sufficiency in {
                "next_decision_from_previous", "conditional_next_step_from_previous",
            }
            conditional_next_step_from_previous = sufficiency == "conditional_next_step_from_previous"
            answering_previous_question = sufficiency == "answers_previous_question"
            if detail_clarification and not answering_previous_question:
                previous_answer_only = False
                next_decision_from_previous = False
                conditional_next_step_from_previous = False
            logger.info(
                "FINN Responses follow-up classification completed in %.2fs, kind=%s",
                monotonic() - classification_started,
                sufficiency if isinstance(sufficiency, str) else "other",
            )
            if detail_clarification and answering_previous_question:
                resolved_detail_clarification = True
                resuming_clarification = False
                model_message = message
        tool_purposes = {
            item["name"]: item.get("description", "")
            for item in FinnResponsesToolCatalog().definitions()
        }

        async def execute(call: FinnResponsesToolCall) -> dict[str, Any]:
            nonlocal selected, target_retry_used, relevance_retry_used, recommended_read_operation
            normalized_message = message.strip().casefold()
            if (
                call.operation_id == "select_asset"
                and normalized_message.endswith("?")
                and normalized_message.startswith((
                    "welke ", "wat ", "which ", "what ", "welches ", "welcher ",
                ))
                and "asset" in normalized_message
                and any(word in normalized_message for word in (
                    "actief", "huidig", "active", "current", "selected", "geselecteerd", "aktiv",
                ))
                and not any(word in normalized_message for word in (
                    "selecteer", "selecteren", "select ", "switch", "change ", "wijzig", "ändere",
                ))
            ):
                return {
                    "status": "retry", "reason": "active_asset_read_not_mutation",
                    "recommended_tool_name": "get_active_asset_context",
                    "instruction": (
                        "The user asks which asset is currently selected. Read the owner-scoped "
                        "active asset with get_active_asset_context; do not propose a selection."
                    ),
                }
            if call.name == "ask_for_clarification":
                prior_read_completed = any(
                    item.get("status") == "completed"
                    and str(item.get("name") or "").startswith("get_")
                    for item in prior_tool_trace
                )
                unbound_reference = (
                    not previous_response
                    and FinnV2RequestPreprocessorService().preprocess(message=message).ambiguous_reference
                )
                if not read_context and not prior_read_completed and not previous_response and not unbound_reference:
                    return {"status": "unavailable", "reason": "read_required_before_clarification"}
                return {
                    "status": "needs_input",
                    "reason": call.inputs["reason"],
                    "question": call.inputs["question"],
                }
            should_check = (
                not pending_operation
                and not resuming_clarification
                and (
                    call.operation_id is not None
                    or (not getattr(self, "model_led_coach", False)
                        and (call.evaluation_operation_id is not None
                             or call.name.startswith("get_")))
                )
                and not conversation_context.get("proposal_revision")
            )
            if should_check and guard is not None:
                contract = (
                    self.proposals.registry.require_supported(call.operation_id or call.evaluation_operation_id)
                    if call.operation_id or call.evaluation_operation_id else None
                )
                purpose = (
                    str(contract.semantic_description or contract.operation_id)
                    if contract and call.evaluation_operation_id
                    else f"{contract.action_polarity.value} {contract.domain}"
                    if contract and contract.action_polarity
                    else tool_purposes.get(call.name, call.name)
                )
                preferred = None
                choose_read = getattr(guard, "preferred_read_operation", None)
                if (call.name.startswith("get_") or call.evaluation_operation_id) and not read_context and callable(choose_read) and recommended_read_operation is None:
                    relevance_started = monotonic()
                    options = [
                        {"operation_id": item.operation_id,
                         "purpose": str(item.semantic_description or item.operation_id)}
                        for item in self.proposals.registry.list()
                        if item.supported and item.mode == "EVALUATE"
                        and item.model_policy == "required" and item.required_scopes
                    ]
                    preferred = await choose_read(
                        message=message,
                        previous_answer=str((previous_response or {}).get("answer") or ""),
                        proposed_tool=call.name,
                        proposed_purpose=str(purpose or call.name),
                        evaluation_options=options,
                        read_options=[
                            {"operation_id": name, "purpose": description}
                            for name, description in tool_purposes.items()
                            if name.startswith("get_")
                        ],
                    )
                    logger.info(
                        "FINN Responses primary-read relevance completed in %.2fs changed=%s",
                        monotonic() - relevance_started, bool(preferred and preferred != call.name),
                    )
                    if preferred and preferred != call.name:
                        if relevance_retry_used:
                            return {"status": "unavailable", "reason": "tool_not_relevant_to_request"}
                        relevance_retry_used = True
                        recommended_read_operation = preferred
                        if preferred == "respond_without_tool":
                            return {
                                "status": "retry", "reason": "primary_operation_mismatch",
                                "finalize_now": True,
                                "instruction": (
                                    "No FINN read or evaluation is needed for this general explanation. "
                                    "Answer the user directly without a tool, personal account facts, "
                                    "current market claims, or an unqualified trading benefit."
                                ),
                            }
                        return {
                            "status": "retry", "reason": "primary_operation_mismatch",
                            "recommended_tool_name": preferred,
                            "instruction": (
                                "The primary operation selected from FINN's existing registry is "
                                f"{preferred}. The proposed tool was not executed. Call that "
                                "operation with its declared arguments; its contract gathers required evidence."
                            ),
                        }
                relevance_started = monotonic()
                aligned = (
                    preferred == call.name
                    or (recommended_read_operation is not None
                        and (call.evaluation_operation_id or call.name) == recommended_read_operation)
                    or await guard.is_relevant(
                    message=message,
                    previous_answer=str((previous_response or {}).get("answer") or ""),
                    tool_name=call.operation_id or call.evaluation_operation_id or call.name,
                    tool_purpose=str(purpose or call.name),
                    is_proposal=call.operation_id is not None,
                    **({"proposal_operations": [
                        {
                            "operation_id": item.operation_id,
                            "domain": item.domain,
                            "polarity": item.action_polarity.value if item.action_polarity else "",
                            "purpose": str(item.semantic_description or item.operation_id),
                        }
                        for item in self.proposals.registry.list()
                        if item.supported and item.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}
                    ]} if call.operation_id else {}),
                    )
                )
                logger.info(
                    "FINN Responses tool relevance completed in %.2fs verified=%s",
                    monotonic() - relevance_started, aligned is not None,
                )
                if aligned is None:
                    return {"status": "unavailable", "reason": "tool_relevance_unverified"}
                if not aligned:
                    if relevance_retry_used:
                        return {"status": "unavailable", "reason": "tool_not_relevant_to_request"}
                    relevance_retry_used = True
                    recommended_operation_id = (
                        getattr(guard, "recommended_operation_id", None)
                        if call.operation_id else None
                    )
                    recommended_tool_name = (
                        catalog.proposal_tool_for_operation(recommended_operation_id)
                        if recommended_operation_id else None
                    )
                    return {
                        "status": "retry", "reason": "tool_not_relevant_to_request",
                        **({"recommended_operation_id": recommended_operation_id,
                            "recommended_tool_name": recommended_tool_name}
                           if recommended_tool_name else {}),
                        "instruction": (
                            "The candidate tool is not the right primary operation for the latest "
                            "request. Reconsider the user's intended outcome and the registry-backed "
                            "evaluation contracts as well as reads; choose the operation that can "
                            "actually answer it. Use a proposal only if a mutation was requested. "
                            "No tool was executed and no proposal was created."
                        ),
                    }
            if call.operation_id is None:
                previous_setup_target: dict[str, object] = {}
                if call.name == "get_active_plan_and_strategy":
                    # The model can express the choice, but only the user's text
                    # and owner-scoped persisted evidence may select the object.
                    reference = call.inputs.get("reference")
                    prior_setups = [
                        item for prior_call in (previous_response or {}).get("tool_trace", [])
                        for item in (prior_call.get("result", {}).get("results") or [])
                        if item.get("scope") == "read_active_setup"
                        and item.get("status") == "completed"
                        and isinstance(item.get("data"), dict)
                        and item["data"].get("setup_id")
                    ]
                    prior_name = str(prior_setups[-1]["data"].get("name") or "") if prior_setups else ""
                    matches_prior_name = bool(
                        prior_name and call.inputs.get("setup_name", "").casefold() == prior_name.casefold()
                    )
                    if reference == "previous_response" or matches_prior_name:
                        if prior_setups:
                            previous_setup_target = {
                                "entity_type": "setup",
                                "entity_id": prior_setups[-1]["data"]["setup_id"],
                            }
                        elif reference == "previous_response":
                            action_result = dict(conversation_context.get("previous_action_result") or {})
                            if (
                                action_result.get("owner_user_id") == self.user_id
                                and action_result.get("result_status") == "succeeded"
                                and action_result.get("entity_type") == "setup"
                                and action_result.get("entity_id") is not None
                            ):
                                previous_setup_target = {
                                    "entity_type": "setup",
                                    "entity_id": action_result["entity_id"],
                                }
                        if reference == "previous_response" and not previous_setup_target and not resuming_clarification:
                            explicit_name = str(call.inputs.get("setup_name") or "")
                            explicit_target = bool(
                                mentioned_catalog_symbols(message)
                                or (explicit_name and explicit_name.casefold() in message.casefold())
                            )
                            if not explicit_target:
                                if previous_response and previous_response.get("answer"):
                                    return {
                                        "status": "retry",
                                        "reason": "previous_response_reference_unavailable",
                                        "finalize_now": True,
                                        "instruction": (
                                            "The previous verified response has no saved setup identity. "
                                            "Do not claim that a setup was read. Answer the latest "
                                            "follow-up only from that verified response and the "
                                            "trader's stated rule, or ask one clarifying question."
                                        ),
                                    }
                                return {"status": "unavailable", "reason": "previous_response_reference_unavailable"}
                    call = replace(call, inputs={
                        key: value for key, value in call.inputs.items()
                        if key not in {"setup_name", "reference"}
                    })
                model_asset = call.inputs.get("asset")
                if model_asset:
                    symbol = resolve_catalog_symbol(model_asset)
                    if symbol not in mentioned_catalog_symbols(message):
                        call = replace(call, inputs={key: value for key, value in call.inputs.items() if key != "asset"})
                    else:
                        call = replace(call, inputs={**call.inputs, "asset": symbol})
                if (
                    "read_active_setup" in call.read_tools
                    and not FinnV2EntityResolutionService.is_setup_collection_request(message)
                ):
                    session_factory = getattr(self.reads, "session_factory", None)
                    if session_factory is not None:
                        async with session_factory() as session:
                            target = await FinnV2EntityResolutionService(session).resolve_canonical_target(
                                user_id=self.user_id, entity_type="setup", message=message,
                                conversation_context=(
                                    {"canonical_entity_target": previous_setup_target}
                                    if previous_setup_target else (
                                        dict(conversation_context)
                                        if FinnV2EntityResolutionService.references_recent_action(message, "setup")
                                        else {}
                                    )
                                ),
                                selector={
                                    **call.inputs,
                                    "asset_source": (
                                        "explicit_message" if call.inputs.get("asset")
                                        and call.inputs["asset"] in mentioned_catalog_symbols(message)
                                        else "context"
                                    ),
                                },
                            )
                        if target.resolution_status == "resolved" and (
                            call.name == "get_active_plan_and_strategy"
                            or target.source == "explicit_name"
                        ):
                            call = replace(call, inputs=(
                                {"setup_id": target.entity_id}
                                if call.name == "get_active_plan_and_strategy"
                                else {**call.inputs, "setup_id": target.entity_id}
                            ))
                if call.evaluation_operation_id and resuming_clarification:
                    chosen_setups = [
                        item for prior_read in read_context
                        for item in (prior_read.get("results") or [])
                        if item.get("scope") == "read_active_setup"
                        and item.get("status") == "completed"
                        and isinstance(item.get("data"), dict)
                        and item["data"].get("setup_id") is not None
                    ]
                    if len({item["data"]["setup_id"] for item in chosen_setups}) == 1:
                        call = replace(call, inputs={
                            **call.inputs, "setup_id": chosen_setups[-1]["data"]["setup_id"],
                        })
                read_identity = (call.name, repr(sorted(call.inputs.items())))
                if call.read_tools and read_identity in completed_read_calls:
                    return {
                        "status": "retry", "reason": "read_already_completed_this_turn",
                        "instruction": (
                            "That same FINN read already returned evidence in this turn. Do not repeat it. "
                            "Use the existing typed result to answer the latest question, or ask one "
                            "specific clarification if a user choice is genuinely missing."
                        ),
                    }
                read_result = await self.reads(call)
                read_context.append(read_result)
                completed_read_calls.add(read_identity)
                return read_result
            if pending_operation and call.operation_id != pending_operation:
                return {"status": "unavailable", "reason": "guided_operation_still_active"}
            if selected is not None:
                return {"status": "unavailable", "reason": "one_proposal_per_run"}
            analysis = self.proposals.from_call(
                call=call,
                message=message,
                conversation_context=conversation_context,
                verified_asset=verified_asset,
                read_context=read_context,
            )
            state = analysis.request_plan.operation_state
            if (
                not pending_operation
                and call.operation_id.startswith(("update_", "delete_", "deactivate_"))
                and self.proposals.registry.require_supported(call.operation_id).domain
                in {"setup", "strategy", "bot"}
            ):
                candidate_domain = self.proposals.registry.require_supported(call.operation_id).domain
                requested_domain: str | None = None
                check_domain = getattr(guard, "requested_mutation_domain", None)
                if callable(check_domain):
                    registry_domains = [
                        {"domain": domain, "purpose": next(
                            str(item.semantic_description or item.operation_id)
                            for item in self.proposals.registry.list()
                            if item.supported and item.domain == domain
                        )}
                        for domain in ("setup", "strategy", "bot")
                    ]
                    requested_domain = await check_domain(
                        message=message, domains=registry_domains,
                    )
                    if requested_domain in {None, "unknown"}:
                        return {"status": "unavailable", "reason": "write_target_domain_unverified"}
                    if requested_domain != candidate_domain:
                        if target_retry_used:
                            return {"status": "unavailable", "reason": "write_target_domain_mismatch"}
                        target_retry_used = True
                        return {
                            "status": "retry",
                            "reason": "requested_object_type_mismatch",
                            "candidate_operation_id": call.operation_id,
                            "target_domain": requested_domain,
                            "instruction": (
                                "The user's requested object kind differs from the candidate. "
                                "Choose only a registry operation for the requested kind; "
                                "if no owner-scoped object exists, ask for clarification."
                            ),
                        }
                session_factory = getattr(self.reads, "session_factory", None)
                # A verified requested kind outranks a prefix match on a saved
                # object's name in another domain (for example a setup whose
                # name prefixes a strategy that has not been created yet).
                if session_factory is not None and requested_domain is None:
                    async with session_factory() as session:
                        resolver = FinnV2EntityResolutionService(session)
                        targets = [
                            await resolver.resolve_canonical_target(
                                user_id=self.user_id, entity_type=entity_type,
                                message=message, conversation_context=dict(conversation_context),
                            )
                            for entity_type in ("setup", "strategy", "bot")
                        ]
                    candidate_name_length = max((
                        len(target.display_name or "") for target in targets
                        if target.entity_type == candidate_domain
                        and target.resolution_status == "resolved"
                        and target.source == "explicit_name"
                    ), default=0)
                    explicit_matches = [
                        target for target in targets
                        if target.entity_type != candidate_domain
                        and target.resolution_status == "resolved"
                        and target.source == "explicit_name"
                        and len(target.display_name or "") > candidate_name_length
                    ]
                    if len(explicit_matches) == 1:
                        if target_retry_used:
                            return {"status": "unavailable", "reason": "write_target_domain_mismatch"}
                        target_retry_used = True
                        return {
                            "status": "retry",
                            "reason": "owner_scoped_target_type_mismatch",
                            "candidate_operation_id": call.operation_id,
                            "target_domain": explicit_matches[0].entity_type,
                            "instruction": (
                                "The saved object named in the request belongs to the indicated domain, "
                                "not the candidate action's domain. Reconsider the requested operation. "
                                "FINN keeps the owner-scoped object ID server-side."
                            ),
                        }
            selected = analysis
            return {
                "status": "needs_input" if state.get("missing_required_inputs") else "validation_pending",
                "operation_id": call.operation_id,
                "supplied_inputs": {
                    key: value for key, value in dict(state.get("collected_inputs") or {}).items()
                    if not key.endswith("_id")
                },
                "missing_inputs": state.get("missing_required_inputs", []),
                "confirmation_required": True,
            }

        async def checkpoint(response_id: str, trace: tuple[dict[str, Any], ...]) -> None:
            session_factory = getattr(self.reads, "session_factory", None)
            if session_factory is None:
                return
            async with session_factory() as session:
                await FinnV2RuntimeContractRepository(session).record_responses_progress(
                    run_id=self.run_id, user_id=self.user_id,
                    response_id=response_id, tool_trace=list(trace),
                )
                await session.commit()

        use_verified_turn = not resuming_clarification or getattr(self, "model_led_coach", False)
        verified_turn = project_verified_turn(previous_response) if use_verified_turn else None
        loop_started = monotonic()
        loop = FinnResponsesLoop(
            client=self.client, executor=execute, on_tool_result=checkpoint,
            catalog=catalog,
            model=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
            clarification_model=os.getenv("FINN_RESPONSES_CLARIFICATION_MODEL", "gpt-6-luna"),
            reasoning_effort=os.getenv("FINN_RESPONSES_REASONING_EFFORT", "none"),
        )
        result = await loop.run(
            message=model_message or message,
            instructions=(self._model_led_instructions(locale) if getattr(self, "model_led_coach", False) else instructions),
            verified_turn_context=verified_turn,
            previous_response_id=(
                previous_response_id
                if previous_response_id and not resuming_clarification
                and not previous_response_id.startswith("guided-")
                else None
            ),
            previous_verified_answer=str(verified_turn.get("answer") or "")[:1600] if verified_turn else None,
            previous_tool_availability=tuple(
                {"scope": str(item.get("scope") or ""),
                 "status": str(item.get("status") or ""),
                 "reason": str(item.get("reason") or "")}
                for item in verified_turn["evidence"]
            ) if verified_turn else (),
            previous_terminal_status=(
                str(previous_response.get("terminal_status") or "")
                if previous_response and use_verified_turn else None
            ),
            previous_terminal_reason=(
                str(previous_response.get("terminal_reason") or "")
                if previous_response and use_verified_turn else None
            ),
            antecedent_verified_answer=(
                str(previous_response.get("antecedent_verified_answer") or "")[:1600]
                if previous_response and use_verified_turn else None
            ),
            guided_operation_id=pending_operation,
            resuming_clarification=resuming_clarification,
            resumed_clarification_reason=(
                str(pending_clarification.get("reason") or "") or None
            ) if resuming_clarification else None,
            resume_evaluation_operation_id=(
                next((
                    str((item.get("result") or {})["evaluation_operation_id"])
                    for item in reversed((previous_response or {}).get("tool_trace") or [])
                    if (item.get("result") or {}).get("evaluation_operation_id")
                ), None)
                if resuming_clarification else None
            ),
            original_user_request=(
                str(conversation_context.get("responses_clarification", {}).get("original_message") or "")
                if resuming_clarification or resolved_detail_clarification else ""
            ),
            previous_answer_only=previous_answer_only,
            next_decision_from_previous=next_decision_from_previous,
            conditional_next_step_from_previous=conditional_next_step_from_previous,
            answering_previous_question=answering_previous_question,
            conditional_process_check=lambda: bool(
                getattr(guard, "conditional_process", False)
                and getattr(guard, "response_focus", None) != "priorities"
            ),
            response_focus_check=lambda: getattr(guard, "response_focus", None),
            horizon_classification_check=lambda: bool(
                getattr(guard, "horizon_classification_question", False)
            ),
            locale=locale,
            force_read_repair=force_read_repair,
            rejection_feedback=rejection_feedback,
            model_led_coach=getattr(self, "model_led_coach", False),
        )
        logger.info("FINN Responses tool loop completed in %.2fs", monotonic() - loop_started)
        if (
            not individual_proposals
            and selected is None
            and pending_operation is None
            and not force_read_repair
            and not previous_answer_only
            and not result.tool_trace
            and getattr(self, "model_led_coach", False)
            and not _hypothetical_trade_reflection(message)
            and not _read_only_stop_loss_coaching(message)
        ):
            action_contracts = []
            for contract in self.proposals.registry.list():
                if not contract.supported or contract.mode not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
                    continue
                try:
                    loop.catalog.proposal_tool_for_operation(contract.operation_id)
                except FinnResponsesToolError:
                    continue
                action_contracts.append({
                    "operation_id": contract.operation_id,
                    "purpose": contract.semantic_description or contract.operation_id,
                })
            audit = getattr(guard, "requested_action_contract", None)
            missed_operation = (
                await audit(message=message, contracts=action_contracts)
                if callable(audit) and action_contracts else None
            )
            if missed_operation:
                result = await loop.run(
                    message=message,
                    instructions=self._model_led_instructions(locale),
                    previous_response_id=result.response_id,
                    guided_operation_id=missed_operation,
                    locale=locale,
                    model_led_coach=True,
                )
        if (
            getattr(self, "model_led_coach", False)
            and verified_turn is not None
            and not result.tool_trace
            and selected is None
        ):
            result = replace(result, uses_previous_response=True)
        if pending_operation and selected is None:
            raise FinnResponsesError("guided_proposal_tool_call_required")
        recent_action_result = dict(conversation_context.get("previous_action_result") or {})
        if recent_action_result.get("owner_user_id") != self.user_id or recent_action_result.get("result_status") != "succeeded":
            recent_action_result = {}
        return FinnResponsesFrontDoorResult(result, selected, previous_response, recent_action_result or None, locale)
