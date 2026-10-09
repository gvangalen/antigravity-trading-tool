"""Channel-neutral FINN tool surface backed by the canonical operation registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_tool_registry_service import FinnV2ToolRegistryService


# These names are a presentation of existing read scopes and action contracts,
# not a second definition of required inputs or execution policy.
_READ_SCOPES: dict[str, tuple[str, ...]] = {
    "get_my_profile_and_risk_style": ("profile", "preferences"),
    "get_active_asset_context": ("active_asset", "watchlist"),
    "get_active_plan_and_strategy": ("active_setup", "linked_strategy"),
    "get_market_snapshot": ("market_snapshot", "macro_snapshot"),
    "get_indicator_snapshot": ("indicator_configuration",),
    "get_current_technical_snapshot": ("technical_snapshot",),
    "get_portfolio_and_exposure": ("portfolio",),
    "get_decision_history": ("review_history", "latest_report"),
}

_PROPOSAL_OPERATIONS: dict[str, tuple[str, ...]] = {
    "create_or_update_trade_plan_proposal": (
        "create_setup", "update_setup", "delete_setup",
        "create_strategy", "update_strategy", "delete_strategy",
    ),
    "create_indicator_proposal": (
        "create_indicator_configuration", "update_indicator_configuration",
        "delete_indicator_configuration",
    ),
    "create_dca_plan_proposal": ("create_setup",),
    "manage_asset_watchlist_proposal": (
        "select_asset", "watchlist_add", "watchlist_remove",
    ),
    "manage_paper_bot_proposal": (
        "create_bot", "update_bot", "deactivate_bot", "delete_bot", "activate_paper_bot",
    ),
}

_FORBIDDEN_MODEL_FIELDS = frozenset({
    "user_id", "owner_user_id", "tenant_id", "proposal_id", "execution_id",
    "confirmation_id", "idempotency_key", "run_id", "conversation_id",
    "setup_id", "strategy_id", "bot_id",
})
_SERVER_RESOLVED_ENTITY_FIELDS = frozenset({"setup_id", "strategy_id", "bot_id"})


class FinnResponsesToolError(ValueError):
    """A model-selected tool or its arguments failed the server-side boundary."""

    def __init__(self, reason: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.details = details or {}


@dataclass(frozen=True)
class FinnResponsesToolCall:
    name: str
    operation_id: str | None
    inputs: dict[str, Any]
    read_tools: tuple[str, ...]
    required_inputs: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    draft_intent: str | None = None
    evaluation_operation_id: str | None = None
    answer_mode: str | None = None
    setup_names: tuple[str, ...] = ()


class FinnResponsesToolCatalog:
    def __init__(
        self, registry: FinnV2OperationRegistry | None = None, *, individual_proposals: bool = False,
    ) -> None:
        self.registry = registry or FinnV2OperationRegistry()
        self.individual_proposals = individual_proposals
        self.proposal_operations = (
            {f"propose_{operation_id}": (operation_id,)
             for operations in _PROPOSAL_OPERATIONS.values() for operation_id in operations}
            if individual_proposals else _PROPOSAL_OPERATIONS
        )
        self.read_definitions = {
            tool.name: tool for tool in FinnV2ToolRegistryService().list_tools()
        }
        scope_bindings: dict[str, str] = {}
        for contract in self.registry.list():
            for scope, read_tool in contract.scope_tool_bindings:
                scope_bindings[scope] = read_tool
        self.read_tools = {
            name: tuple(scope_bindings[scope] for scope in scopes)
            for name, scopes in _READ_SCOPES.items()
        }
        # Collection reads have a distinct typed read adapter. They do not
        # add a new action/evaluation operation to the sealed registry matrix.
        self.read_tools["get_saved_setup_inventory"] = ("read_saved_setup_inventory",)
        self.read_tools["get_saved_setup"] = ("read_active_setup",)
        self.read_tools["get_current_asset_scores"] = ("read_active_asset", "read_asset_scores")
        self.read_tools["get_setup_market_matches"] = ("read_setup_market_matches",)
        self.read_tools["get_linked_strategies"] = ("read_active_setup", "read_linked_strategies")
        self.evaluation_contracts = {
            contract.operation_id: contract
            for contract in self.registry.list()
            if contract.supported and contract.mode == "EVALUATE"
            and contract.model_policy == "required" and contract.required_scopes
        }
        for operations in _PROPOSAL_OPERATIONS.values():
            for operation_id in operations:
                contract = self.registry.require_supported(operation_id)
                if contract.mode not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
                    raise FinnResponsesToolError("proposal_binding_is_not_an_action_contract")

    def proposal_tool_for_operation(self, operation_id: str) -> str:
        for name, operations in self.proposal_operations.items():
            if operation_id in operations:
                return name
        raise FinnResponsesToolError("guided_operation_not_in_tool_catalog")

    def definitions(
        self, *, guided_operation_id: str | None = None,
        retry_target_domain: str | None = None,
        retry_operation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        definitions.append({
            "type": "function",
            "name": "ask_for_clarification",
            "description": (
                "Use only when a specific choice or user-provided detail is necessary to answer the "
                "current question and cannot be obtained from FINN read tools. Ask one short natural "
                "question. If a general yes/no boundary can be answered without that detail, "
                "answer it directly and ask the detail only if needed afterward. Do not use "
                "this for unavailable market data; state that limitation instead."
            ),
            "strict": False,
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "One user-facing question without internal fields or IDs."},
                    "reason": {"type": "string", "enum": ["choice_required", "user_detail_required"]},
                },
                "required": ["question", "reason"],
                "additionalProperties": False,
            },
        })
        for name, read_tools in self.read_tools.items():
            description = " ".join(self.read_definitions[tool].description for tool in read_tools)
            if name == "get_active_asset_context":
                description += (
                    " Returns the resolved asset symbol and its context source separately from "
                    "watchlist membership. A selected asset does not imply an owned position, "
                    "a fresh market quote, or a trading recommendation."
                )
            if name == "get_my_profile_and_risk_style":
                description += (
                    " Call only when the answer needs this user's saved profile or risk style. "
                    "A general explanation of a trading concept does not need this read. "
                    "Optional trader_context is user-written coaching preference, not proof of a saved trade rule, "
                    "account balance or market fact. "
                    "This returns preferences, not a judgment about whether a specific plan "
                    "or proposed amount fits them; use the registry-backed evaluate_plan "
                    "tool for that assessment."
                )
            if name == "get_active_plan_and_strategy":
                description += (
                    " Returns one selected saved setup and its linked strategy, not a list or assessment. "
                    "For only a saved setup's market, macro or technical score boundaries, "
                    "use get_saved_setup: those fields are on the setup and do not require a strategy. "
                    "For a single saved DCA plan, read this tool to verify its base amount, score bands "
                    "and a hypothetical planned amount; those fields belong to the linked strategy. "
                    "The returned dca_score_bands are calculated by the execution curve engine: "
                    "from_score_inclusive includes the exact threshold, while to_score_exclusive does not. "
                    "Use the returned planned_amount for a hypothetical score instead of guessing the boundary. "
                    "For all saved setups, counts, or questions about which of several setups has a field, "
                    "use get_saved_setup_inventory instead. "
                    "Use it for listing settings or static arithmetic from saved entry, "
                    "stop and targets. If the user asks whether the complete plan fits "
                    "their goals or risk style, use evaluate_plan instead; this read alone "
                    "cannot establish suitability or a current trade signal."
                )
            if name == "get_saved_setup":
                description += (
                    " Read one owner-scoped saved setup by its name, including its market, macro "
                    "and technical minimum and maximum score boundaries. These are setup fields, "
                    "independent of how many strategies are linked. Do not read or choose a strategy "
                    "to answer a question only about these setup fields."
                )
            if name == "get_current_asset_scores":
                description += (
                    " Read the owner's current market, macro and technical component scores "
                    "for one asset using the same source verification as Analyse. "
                    "reported_scores is null for each missing or stale component; "
                    "component_source_status explains why; component_source_observed_at "
                    "contains each configured indicator's actual source moment when available. "
                    "A missing score is not zero. "
                    "benchmark_score is null unless all three components are fresh. "
                    "Do not present historical stored scores as current."
                )
            if name == "get_saved_setup_inventory":
                description += (
                    " Returns an owner-scoped collection, optionally filtered by asset and timeframe; "
                    "For one explicitly named DCA setup with answer_mode=explain, FINN also reads its "
                    "linked strategy so the saved amount rule can be explained. "
                    "the typed complete flag reports whether repository pagination truncated it. "
                    "Use for all setup names, counts and comparisons, including a follow-up about "
                    "'those three' after listing setups. For a comparison of exactly two "
                    "user-selected setups, the server also reads each linked strategy and reports "
                    "its availability separately. A general list read does not select an active setup "
                    "or read linked strategies. For a comparison, provide answer_mode=compare and "
                    "the two user-named setup names in setup_names. The server resolves names to "
                    "owner-scoped records; do not invent an ID or replace one named setup with another. "
                    "When the user chooses one linked strategy for a comparison, pass its exact "
                    "name in strategy_name; FINN checks its owner and setup relation."
                )
            if name == "get_setup_market_matches":
                description += (
                    " Use for questions about which of the user's setups currently matches measured "
                    "market conditions or deserves attention. Distinguish benchmark_score, weighted "
                    "by the owner's current Analyse preferences, from each setup's weighted fit to its "
                    "saved score ranges. Neither establishes an entry trigger, strategy readiness "
                    "or permission to trade. reported_scores include only components whose "
                    "sources are currently verified, matching Analyse. Use "
                    "component_source_status and as_of to explain that distinction. The saved "
                    "score boundaries are in each match's conditions even when no match can be scored. "
                    "If source_status is not available, explain the data gap."
                )
            if name == "get_linked_strategies":
                description += (
                    " Use when the user asks which or how many strategies belong to one saved setup. "
                    "Returns every owner-scoped linked strategy, without silently choosing one. "
                    "Pass the setup name visible in this request; for a follow-up, use the prior "
                    "verified setup reference. Do not substitute a different setup."
                )
            properties = {
                "asset": {"type": ["string", "null"], "description": "Asset named by the user, if any."},
                "timeframe": {"type": ["string", "null"], "description": "A real timeframe such as 4H or 1D, never an object name."},
            }
            if name in {"get_active_plan_and_strategy", "get_linked_strategies", "get_saved_setup"}:
                properties.update({
                    "setup_name": {"type": ["string", "null"],
                                   "description": "Saved setup name explicitly selected by the user. FINN resolves ownership server-side."},
                    "reference": {"type": ["string", "null"],
                                  "enum": ["current_request", "previous_response", None],
                                  "description": "Use previous_response only to revisit the owner-scoped setup read in the preceding verified answer."},
                })
            if name == "get_active_plan_and_strategy":
                properties.update({
                    "strategy_name": {"type": ["string", "null"],
                                      "description": "Saved strategy name explicitly selected by the user, only when named in the latest request. FINN verifies its owner and setup link."},
                })
            if name == "get_saved_setup_inventory":
                properties.update({
                    "answer_mode": {"type": ["string", "null"],
                                    "enum": ["list", "compare", "explain", None]},
                    "setup_names": {"type": ["array", "null"],
                                    "items": {"type": "string"},
                                    "description": "Exactly the user-named setups to compare, or null when listing."},
                    "strategy_name": {"type": ["string", "null"],
                                      "description": "One strategy explicitly named by the user for a comparison. FINN binds it to its owner-scoped setup."},
                })
            definitions.append({
                "type": "function",
                "name": name,
                "description": description,
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            })
        definitions.append({
            "type": "function",
            "name": "get_open_dca_draft",
            "description": (
                "Read the latest owner-scoped, unconfirmed DCA proposal in this conversation. "
                "Use for questions about its staffel, base amount or hypothetical score, "
                "including follow-ups after a coach answer. This is a draft, not a saved plan "
                "or an instruction to buy. If a benchmark component is missing, Smart DCA "
                "cannot compute a planned amount and must hold."
            ),
            "strict": True,
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        })
        for contract in self.evaluation_contracts.values():
            optional_properties = {}
            if "hypothetical_change" in contract.optional_inputs:
                optional_properties["hypothetical_change"] = {
                    "type": "string",
                    "description": (
                        "A change the user is considering, quoted as a hypothetical scenario. "
                        "It is not a saved plan, an instruction to write, or proof of suitability."
                    ),
                }
            definitions.append({
                "type": "function",
                "name": contract.operation_id,
                "description": (
                    f"Read-only evidence collection for {contract.semantic_description or contract.operation_id} "
                    "Use for a personal assessment, not merely to list saved settings. "
                    "General coaching about a hypothetical stop, position size, or trading "
                    "impulse needs no personal assessment; answer it directly unless the user "
                    "asks you to judge a specific saved plan. "
                    "A request only for static arithmetic from already saved levels "
                    "belongs to the owner-scoped plan/strategy read, not this assessment. "
                    "FINN collects the registry-required sources; missing or stale sources limit the judgment. "
                    "If the user proposes a change, pass it as hypothetical_change when this contract allows it. "
                    "This tool cannot modify stored objects or execute actions."
                ),
                "strict": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset": {"type": "string", "description": "Asset explicitly named by the user, if any."},
                        "timeframe": {"type": "string", "description": "Timeframe explicitly named by the user, if any."},
                        **optional_properties,
                    },
                    "additionalProperties": False,
                },
            })
        for name, operations in self.proposal_operations.items():
            if guided_operation_id and guided_operation_id not in operations:
                continue
            contracts = [
                self.registry.require_supported(operation_id)
                for operation_id in operations
                if (not guided_operation_id or operation_id == guided_operation_id)
                and (not retry_operation_id or operation_id == retry_operation_id)
                and (not retry_target_domain or self.registry.require_supported(operation_id).domain == retry_target_domain)
            ]
            if not contracts:
                continue
            variants: list[dict[str, Any]] = []
            for contract in contracts:
                field_types: dict[str, str] = {}
                for field in contract.input_fields:
                    if field in _FORBIDDEN_MODEL_FIELDS or field in contract.server_resolved_inputs:
                        continue
                    field_type = contract.input_json_type(field)
                    if field_type is None:
                        raise FinnResponsesToolError(f"registry_input_type_missing:{contract.operation_id}:{field}")
                    field_types[field] = field_type
                variants.append({
                    "type": "object",
                    "properties": {
                        "operation_id": {"type": "string", "enum": [contract.operation_id]},
                        "draft_intent": {
                            "type": "string", "enum": ["new", "revise"],
                            "description": "Revise only a pending draft in this conversation.",
                        },
                        "inputs": {
                            "type": "object",
                            "description": (
                                "Put requested edits inside changed_fields."
                                if "changed_fields" in contract.input_fields
                                else "Supply only known fields; FINN asks for missing inputs."
                            ),
                            "properties": {
                                field: {
                                    "type": field_type,
                                    **({"enum": list(contract.allowed_values_for(field))}
                                       if contract.allowed_values_for(field) else {}),
                                }
                                for field, field_type in sorted(field_types.items())
                            },
                            "additionalProperties": False,
                        },
                    },
                    "required": ["operation_id", "inputs", "draft_intent"],
                    "additionalProperties": False,
                })
            definitions.append({
                "type": "function",
                "name": name,
                "description": "Target saved object types: "
                + ", ".join(sorted({contract.domain for contract in contracts}))
                + ". Use this as the first tool for an explicit request to change one of these objects; "
                "related parent or child objects are context, not the mutation target. "
                "Prepare, never execute, a confirmation-required FINN proposal only when "
                "the user explicitly asks to create, change, or delete a saved object. A question about "
                "whether an action fits a plan or what it would mean is a read/evaluation request, "
                "not permission to draft a change. Contracts: "
                + "; ".join(
                    f"{contract.operation_id}: {contract.semantic_description or contract.operation_id} "
                    f"Required model inputs: "
                    f"{', '.join(field for field in contract.required_inputs if field not in _FORBIDDEN_MODEL_FIELDS) or 'none'}. "
                    f"FINN resolves server-side: "
                    f"{', '.join(field for field in contract.required_inputs if field in _FORBIDDEN_MODEL_FIELDS) or 'none'}. "
                    f"Model-supplied fields allowed for this operation: "
                    f"{', '.join(field for field in contract.input_fields if field not in _FORBIDDEN_MODEL_FIELDS) or 'none'}. "
                    + (
                        "This update contract requires changed_fields as one object containing only the "
                        "requested changes; do not put create fields at the top level."
                        if "changed_fields" in contract.input_fields else ""
                    )
                    for contract in contracts
                )
                + " Include every required input explicitly present in the user's request. "
                "Leave genuinely missing inputs out so FINN can ask for them. "
                "Do not put an object's natural name into a different input field to stand in for a "
                "server-resolved object ID; FINN resolves owner-scoped object references from the user message. "
                "Use draft_intent=revise only when changing an unconfirmed proposal draft in this conversation; "
                "updating an existing saved object is draft_intent=new.",
                "strict": False,
                "parameters": {
                    "type": "object",
                    "properties": {"payload": variants[0] if len(variants) == 1 else {"oneOf": variants}},
                    "required": ["payload"],
                    "additionalProperties": False,
                },
            })
        if guided_operation_id:
            guided_name = self.proposal_tool_for_operation(guided_operation_id)
            return [definition for definition in definitions if definition["name"] == guided_name]
        if retry_target_domain:
            return [definition for definition in definitions if self.is_proposal_tool(definition["name"])]
        return definitions

    def is_proposal_tool(self, name: str) -> bool:
        return name in self.proposal_operations

    def validate(self, name: str, arguments: dict[str, Any]) -> FinnResponsesToolCall:
        if not isinstance(arguments, dict):
            raise FinnResponsesToolError("tool_arguments_invalid")
        if name == "answer_directly":
            if set(arguments).difference({"uses_previous_response"}) or any(
                not isinstance(value, bool) for value in arguments.values()
            ):
                raise FinnResponsesToolError("direct_answer_arguments_invalid")
            return FinnResponsesToolCall(name, None, arguments, (), (), ())
        if name == "ask_for_clarification":
            if set(arguments) != {"question", "reason"}:
                raise FinnResponsesToolError("clarification_arguments_invalid")
            question = arguments["question"]
            if (
                not isinstance(question, str) or not 8 <= len(question.strip()) <= 240
                or not question.strip().endswith("?")
                or any(token in question.casefold() for token in ("operation_id", "setup_id", "strategy_id", "bot_id", "required_inputs"))
                or arguments["reason"] not in {"choice_required", "user_detail_required"}
            ):
                raise FinnResponsesToolError("clarification_question_invalid")
            return FinnResponsesToolCall(name, None, {
                "question": question.strip(), "reason": arguments["reason"],
            }, (), (), ())
        if name == "get_open_dca_draft":
            if arguments:
                raise FinnResponsesToolError("draft_read_arguments_invalid")
            return FinnResponsesToolCall(name, None, {}, (), (), ())
        if name in self.read_tools or name in self.evaluation_contracts:
            allowed = {"asset", "timeframe"}
            if name in self.evaluation_contracts:
                allowed.update(self.evaluation_contracts[name].optional_inputs)
            if name in {"get_active_plan_and_strategy", "get_linked_strategies", "get_saved_setup"}:
                allowed.update({"setup_name", "reference"})
            if name == "get_active_plan_and_strategy":
                allowed.add("strategy_name")
            if name == "get_saved_setup_inventory":
                allowed.update({"answer_mode", "setup_names", "strategy_name"})
            if set(arguments).difference(allowed):
                raise FinnResponsesToolError("read_arguments_invalid")
            raw_names = arguments.get("setup_names")
            if raw_names is not None and (
                name != "get_saved_setup_inventory" or not isinstance(raw_names, list)
                or len(raw_names) > 2 or any(not isinstance(item, str) or not item.strip() for item in raw_names)
            ):
                raise FinnResponsesToolError("read_arguments_invalid")
            if any(value is not None and not isinstance(value, str)
                   for key, value in arguments.items() if key != "setup_names"):
                raise FinnResponsesToolError("read_arguments_invalid")
            answer_mode = arguments.get("answer_mode")
            if answer_mode is not None and answer_mode not in {"list", "compare", "explain"}:
                raise FinnResponsesToolError("read_answer_mode_invalid")
            supplied = {
                key: value.strip() for key, value in arguments.items()
                if key not in {"answer_mode", "setup_names"} and isinstance(value, str) and value.strip()
            }
            if len(supplied.get("hypothetical_change", "")) > 500:
                raise FinnResponsesToolError("read_arguments_invalid")
            if "reference" in supplied and supplied["reference"] not in {"current_request", "previous_response"}:
                raise FinnResponsesToolError("read_reference_invalid")
            if "timeframe" in supplied:
                canonical_timeframe = FinnV2SetupInputCatalog.canonical_timeframe(supplied["timeframe"])
                if canonical_timeframe is None:
                    raise FinnResponsesToolError("read_timeframe_invalid")
                supplied["timeframe"] = canonical_timeframe
            if name in self.evaluation_contracts:
                contract = self.evaluation_contracts[name]
                return FinnResponsesToolCall(
                    name, None, supplied, contract.tool_names, (), (),
                    evaluation_operation_id=name,
                )
            return FinnResponsesToolCall(
                name, None, supplied, self.read_tools[name], (), (),
                answer_mode=answer_mode,
                setup_names=tuple(item.strip() for item in (raw_names or [])),
            )
        operations = self.proposal_operations.get(name)
        if operations is None:
            raise FinnResponsesToolError("tool_unknown")
        if set(arguments) == {"payload"} and isinstance(arguments["payload"], dict):
            arguments = arguments["payload"]
        if set(arguments).difference({"operation_id", "inputs", "draft_intent"}):
            raise FinnResponsesToolError("proposal_arguments_invalid")
        draft_intent = arguments.get("draft_intent")
        if draft_intent is not None and draft_intent not in {"new", "revise"}:
            raise FinnResponsesToolError("proposal_draft_intent_invalid")
        operation_id = arguments.get("operation_id")
        if operation_id not in operations:
            recommended_tool = (
                self.proposal_tool_for_operation(operation_id)
                if isinstance(operation_id, str)
                and any(operation_id in bound for bound in self.proposal_operations.values())
                else None
            )
            raise FinnResponsesToolError(
                "operation_not_allowed_for_tool",
                details={"recommended_tool_name": recommended_tool} if recommended_tool else {},
            )
        contract = self.registry.require_supported(operation_id)
        supplied = arguments.get("inputs")
        if not isinstance(supplied, dict):
            raise FinnResponsesToolError("proposal_inputs_invalid")
        if set(supplied).intersection(contract.server_resolved_inputs):
            raise FinnResponsesToolError("server_resolved_input_in_model_arguments")
        if (_FORBIDDEN_MODEL_FIELDS - _SERVER_RESOLVED_ENTITY_FIELDS).intersection(supplied):
            raise FinnResponsesToolError("server_owned_identity_in_model_arguments")
        # A model may echo an ID returned by a read tool, but it cannot select
        # the write target. The existing owner-scoped resolver chooses it anew.
        supplied = {field: value for field, value in supplied.items() if field not in _SERVER_RESOLVED_ENTITY_FIELDS}
        if set(supplied).difference(contract.input_fields):
            raise FinnResponsesToolError(
                "proposal_input_not_in_action_contract",
                details={
                    "operation_id": operation_id,
                    "allowed_inputs": [field for field in contract.input_fields if field not in _FORBIDDEN_MODEL_FIELDS],
                    "required_inputs": list(contract.required_inputs),
                },
            )
        # Responses can emit placeholders for fields it could not infer. They
        # are not supplied contract values and must not advance guided state.
        supplied = {
            field: value for field, value in supplied.items()
            if value not in (None, "", [], {})
            and not (field in contract.required_inputs and type(value) in {int, float} and value == 0)
        }
        supplied = {
            field: FinnV2OperationStateService._canonical_input(field, value) or value
            for field, value in supplied.items()
        }
        for field, value in supplied.items():
            field_type = contract.input_json_type(field)
            valid = {
                "string": lambda item: isinstance(item, str),
                "integer": lambda item: type(item) is int,
                "number": lambda item: type(item) in {int, float},
                "boolean": lambda item: type(item) is bool,
                "object": lambda item: isinstance(item, dict),
                "array": lambda item: isinstance(item, list),
            }[field_type](value)
            if not valid:
                raise FinnResponsesToolError(f"proposal_input_type_invalid:{field}")
            allowed_values = contract.allowed_values_for(field)
            if allowed_values and value not in allowed_values:
                raise FinnResponsesToolError(
                    f"proposal_input_value_invalid:{field}",
                    details={"field": field, "allowed_values": list(allowed_values)},
                )
        if name == "create_dca_plan_proposal" and supplied.get("setup_type") is not None and str(supplied["setup_type"]).casefold() != "dca":
            alternatives = [
                tool_name for tool_name, allowed in self.proposal_operations.items()
                if tool_name != name and operation_id in allowed
            ]
            raise FinnResponsesToolError(
                "dca_tool_requires_dca_setup_contract",
                details={"recommended_tool_name": alternatives[0]} if len(alternatives) == 1 else {},
            )
        required = contract.required_inputs_for(supplied)
        missing = tuple(field for field in required if supplied.get(field) in (None, "", [], {}))
        return FinnResponsesToolCall(name, operation_id, dict(supplied), (), required, missing, draft_intent)
