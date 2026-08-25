"""Canonical FINN V2 operation contracts.

This module deliberately owns the operation decisions that used to be spread
across request analysis, domain requirements, planning and policy.  Runtime
services may consume a contract but must not add scopes, tools or write rules.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional

from backend.domain.finn_v2_contract import INFORMATION_SCOPE_ORDER


# This is the sole scope-to-tool binding used while materializing contracts.
# Runtime services consume the persisted bindings on the resolved contract.
_SCOPE_TOOL_BINDINGS = {
    "profile": "read_profile",
    "preferences": "read_user_preferences",
    "active_asset": "read_active_asset",
    "watchlist": "read_watchlist",
    "indicator_configuration": "read_indicator_configuration",
    "market_snapshot": "read_market_snapshot",
    "active_setup": "read_active_setup",
    "linked_strategy": "read_linked_strategy",
    "linked_bot": "read_linked_bot",
    "bot_status": "read_bot_status",
    "portfolio": "read_portfolio",
    "latest_report": "read_latest_report",
    "review_history": "read_review_history",
}

# Response fields are deliberately separate from evidence scopes.  A contract
# can require a graph answer to visibly name its resolved entities without
# turning those presentation requirements into additional tool requirements.
_RESPONSE_FIELDS = frozenset(
    {
        "asset",
        "indicator_configuration",
        "setup",
        "timeframe",
        "strategy",
        "bot",
        "bot_status",
        "observation",
        "evidence",
        "next_step",
    }
)


class FinnV2OperationContractError(ValueError):
    code = "finn_v2_operation_contract_invalid"


class FinnV2OperationUnavailableError(FinnV2OperationContractError):
    code = "finn_v2_operation_not_supported"


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    version: str
    domain: str
    mode: str
    aliases: tuple[str, ...]
    semantic_description: str = ""
    # Selection metadata belongs to the same immutable contract as scopes and
    # policy. The request selector may rank candidates with it, but cannot use
    # it to invent a mode, tool or operation outside this manifest.
    positive_examples: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    required_discourse_acts: tuple[str, ...] = ()
    required_entities: tuple[str, ...] = ()
    any_entities: tuple[str, ...] = ()
    selection_focus_entities: tuple[str, ...] = ()
    allowed_action_polarities: tuple[str, ...] = ()
    selection_required_terms: tuple[str, ...] = ()
    requires_verified_context: bool = False
    ambiguity_rule: str = "clarify"
    selection_priority: int = 0
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    optional_scopes: tuple[str, ...] = ()
    scope_tool_bindings: tuple[tuple[str, str], ...] = ()
    model_policy: str = "never"  # never | optional | required
    response_strategy: str = "deterministic_structured_summary"
    policy_class: str = "read"
    proposal_type: Optional[str] = None
    confirmation_required: bool = False
    execution_adapter: Optional[str] = None
    idempotency_rule: Optional[str] = None
    postcondition: Optional[str] = None
    verifier_rules: tuple[str, ...] = ("grounded", "mode_pure")
    # These are semantic response fields, not additional evidence scopes.
    # They prevent a graph response from silently omitting an entity that was
    # successfully collected and verified.
    required_response_fields: tuple[str, ...] = ()
    allowed_terminal_outcomes: tuple[str, ...] = ("completed", "clarification_required", "unavailable")
    supported: bool = True
    capability_gap: Optional[str] = None

    def __post_init__(self) -> None:
        # Bindings are materialized on the immutable contract so downstream
        # services consume one resolved scope-to-tool map, never a local mode map.
        if not self.scope_tool_bindings:
            object.__setattr__(
                self,
                "scope_tool_bindings",
                tuple(
                    (scope, _SCOPE_TOOL_BINDINGS[scope])
                    for scope in self.required_scopes
                    if scope != "capability"
                ),
            )
        if self.mode not in {
            "CAPABILITY", "READ", "EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL",
            "CLARIFICATION", "CONFIRMATION", "EXECUTION", "UNAVAILABLE",
        }:
            raise FinnV2OperationContractError(f"invalid_mode:{self.operation_id}:{self.mode}")
        if set(self.required_scopes).intersection(self.optional_scopes):
            raise FinnV2OperationContractError(f"scope_overlap:{self.operation_id}")
        if set(self.required_inputs).intersection(self.optional_inputs):
            raise FinnV2OperationContractError(f"input_overlap:{self.operation_id}")
        unknown = set(self.required_scopes + self.optional_scopes).difference(INFORMATION_SCOPE_ORDER)
        if unknown:
            raise FinnV2OperationContractError(f"unknown_scope:{self.operation_id}:{sorted(unknown)}")
        unknown_response_fields = set(self.required_response_fields).difference(_RESPONSE_FIELDS)
        if unknown_response_fields:
            raise FinnV2OperationContractError(
                f"unknown_response_field:{self.operation_id}:{sorted(unknown_response_fields)}"
            )
        if self.model_policy not in {"never", "optional", "required"}:
            raise FinnV2OperationContractError(f"invalid_model_policy:{self.operation_id}")
        write = self.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}
        if write and self.supported and (not self.proposal_type or not self.confirmation_required):
            raise FinnV2OperationContractError(f"write_contract_incomplete:{self.operation_id}")
        if self.execution_adapter and not self.idempotency_rule:
            raise FinnV2OperationContractError(f"adapter_without_idempotency:{self.operation_id}")
        bindings = dict(self.scope_tool_bindings)
        if len(bindings) != len(self.scope_tool_bindings):
            raise FinnV2OperationContractError(f"duplicate_scope_binding:{self.operation_id}")
        missing_bindings = set(self.required_scopes).difference({"capability"}, bindings)
        if missing_bindings:
            raise FinnV2OperationContractError(f"missing_scope_binding:{self.operation_id}:{sorted(missing_bindings)}")

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(tool for scope, tool in self.scope_tool_bindings if scope in self.required_scopes)


class FinnV2OperationRegistry:
    VERSION = "2026-08-23.operation-contracts.v1"

    def __init__(self) -> None:
        self._contracts = {
            contract.operation_id: self._with_selection_metadata(contract)
            for contract in _CONTRACTS
        }
        self._validate_manifest()

    def get(self, operation_id: str) -> OperationContract:
        contract = self._contracts.get(str(operation_id or "").strip())
        if contract is None:
            raise FinnV2OperationUnavailableError(f"unknown_operation:{operation_id}")
        return contract

    def require_supported(self, operation_id: str) -> OperationContract:
        contract = self.get(operation_id)
        if not contract.supported:
            raise FinnV2OperationUnavailableError(contract.capability_gap or f"unsupported_operation:{operation_id}")
        return contract

    def list(self) -> tuple[OperationContract, ...]:
        return tuple(self._contracts.values())

    def candidate_operations(
        self,
        *,
        entities: tuple[str, ...],
        action_polarity: str,
        discourse_act: str,
        has_verified_context: bool,
        normalized_text: str,
        primary_entity: Optional[str] = None,
    ) -> tuple[OperationContract, ...]:
        """Return manifest-approved candidates, never a second intent map."""
        entity_set = set(entities)
        candidates = []
        for contract in self._contracts.values():
            if not contract.supported or contract.operation_id in {"clarify_request", "unavailable"}:
                continue
            # A contract without declared selection metadata is deliberately
            # not eligible for a new natural-language run. Capability gaps and
            # historical-only contracts must never become accidental defaults.
            if not any((
                contract.required_discourse_acts,
                contract.required_entities,
                contract.any_entities,
                contract.allowed_action_polarities,
                contract.requires_verified_context,
            )):
                continue
            if contract.requires_verified_context and not has_verified_context:
                continue
            if contract.required_discourse_acts and discourse_act not in contract.required_discourse_acts:
                continue
            if contract.allowed_action_polarities and action_polarity not in contract.allowed_action_polarities:
                continue
            if contract.selection_required_terms and not all(
                term in normalized_text for term in contract.selection_required_terms
            ):
                continue
            if contract.required_entities and not set(contract.required_entities).issubset(entity_set):
                continue
            if contract.any_entities and not set(contract.any_entities).intersection(entity_set):
                continue
            candidates.append(contract)
        return tuple(sorted(
            candidates,
            key=lambda item: self.candidate_rank(item, primary_entity=primary_entity),
            reverse=True,
        ))

    @staticmethod
    def candidate_rank(contract: OperationContract, *, primary_entity: Optional[str]) -> tuple[int, int]:
        """Return the manifest rank used by both selection and ambiguity checks."""
        return (
            int(bool(primary_entity and primary_entity in contract.selection_focus_entities)),
            contract.selection_priority,
        )

    def resolve_alias(self, text: str) -> Optional[OperationContract]:
        normalized = str(text or "").casefold()
        matches = [contract for contract in self._contracts.values() if any(alias in normalized for alias in contract.aliases)]
        return max(matches, key=lambda item: len(max(item.aliases, key=len))) if matches else None

    @staticmethod
    def _with_selection_metadata(contract: OperationContract) -> OperationContract:
        metadata = _OPERATION_SELECTION_METADATA.get(contract.operation_id, {})
        return replace(contract, **metadata) if metadata else contract

    def _validate_manifest(self) -> None:
        if len(self._contracts) != len(_CONTRACTS):
            raise FinnV2OperationContractError("duplicate_operation_id")
        for contract in self._contracts.values():
            if contract.supported:
                for scope in contract.required_scopes:
                    if scope != "capability":
                        if scope not in _SCOPE_TOOL_BINDINGS:
                            raise FinnV2OperationContractError(
                                f"missing_scope_binding:{contract.operation_id}:{scope}"
                            )
            if contract.operation_id in {"confirm_proposal", "execute_proposal"}:
                if contract.execution_adapter is not None or contract.proposal_type not in {"confirmation", "execution"}:
                    raise FinnV2OperationContractError(
                        f"invalid_workflow_contract:{contract.operation_id}"
                    )


def _read(
    operation_id: str,
    domain: str,
    scopes: tuple[str, ...],
    aliases: tuple[str, ...],
    response_fields: tuple[str, ...] = (),
) -> OperationContract:
    return OperationContract(
        operation_id, FinnV2OperationRegistry.VERSION, domain, "READ", aliases,
        required_scopes=scopes, required_response_fields=response_fields,
    )


def _gap(operation_id: str, domain: str, mode: str, aliases: tuple[str, ...], reason: str) -> OperationContract:
    return OperationContract(operation_id, FinnV2OperationRegistry.VERSION, domain, mode, aliases, supported=False, capability_gap=reason)


# Selection constraints are part of the same manifest as each executable
# contract.  They intentionally describe concepts and discourse, rather than
# encoding a list of production prompt strings in the runtime selector.
_OPERATION_SELECTION_METADATA: Mapping[str, dict] = {
    "capability": {
        "semantic_description": "Explain FINN's supported reads, analyses, proposals and safe actions.",
        "positive_examples": ("Wat kan FINN doen?", "Welke analyses ondersteun je?"),
        "negative_examples": ("Onderbouw die conclusie.", "Beoordeel mijn plan."),
        "required_discourse_acts": ("capability",),
        "selection_priority": 100,
    },
    "explain_previous_evidence": {
        "required_discourse_acts": ("evidence_follow_up",),
        "requires_verified_context": True,
        "selection_priority": 100,
    },
    "reformulate_previous_response": {
        "required_discourse_acts": ("reformulation",),
        "requires_verified_context": True,
        "selection_priority": 100,
    },
    "read_active_asset": {
        "any_entities": ("asset",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 20,
        "selection_focus_entities": ("asset",),
    },
    "read_indicator_configuration": {
        "any_entities": ("indicator_configuration",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 40,
        "selection_focus_entities": ("indicator_configuration",),
    },
    "read_active_setup": {
        "any_entities": ("setup",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 30,
        "selection_focus_entities": ("setup",),
    },
    "read_linked_strategy": {
        "any_entities": ("strategy",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 31,
        "selection_focus_entities": ("strategy",),
    },
    "read_linked_bot": {
        "any_entities": ("bot",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 30,
        "selection_focus_entities": ("bot",),
    },
    "read_bot_status": {
        "required_entities": ("bot_status",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 35,
        "selection_focus_entities": ("bot",),
    },
    "read_watchlist": {
        "any_entities": ("watchlist",),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 30,
        "selection_focus_entities": ("watchlist",),
    },
    "read_active_plan": {
        "required_entities": ("setup", "strategy", "bot"),
        "required_discourse_acts": ("information_request",),
        "allowed_action_polarities": ("read",),
        "selection_priority": 80,
        "selection_focus_entities": ("plan",),
    },
    "evaluate_plan": {
        # Plan evaluation is deliberately distinct from evaluating a single
        # setup, strategy, bot or indicator configuration.
        "any_entities": ("plan",),
        "required_discourse_acts": ("evaluation",),
        "allowed_action_polarities": ("evaluate", "read"),
        "selection_priority": 80,
        "selection_focus_entities": ("plan",),
    },
    "evaluate_indicator_configuration": {
        "any_entities": ("indicator_configuration",),
        "required_discourse_acts": ("evaluation",),
        "selection_priority": 40,
        "selection_focus_entities": ("indicator_configuration",),
    },
    "evaluate_setup": {
        "any_entities": ("setup",),
        "required_discourse_acts": ("evaluation",),
        "selection_priority": 40,
        "selection_focus_entities": ("setup",),
    },
    "evaluate_strategy": {
        "any_entities": ("strategy",),
        "required_discourse_acts": ("evaluation",),
        "selection_priority": 40,
        "selection_focus_entities": ("strategy",),
    },
    "evaluate_bot": {
        "any_entities": ("bot",),
        "required_discourse_acts": ("evaluation",),
        "selection_priority": 40,
        "selection_focus_entities": ("bot",),
    },
    "create_setup": {
        "any_entities": ("setup",),
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("create", "add"),
        "selection_priority": 80,
    },
    "watchlist_add": {
        "any_entities": ("watchlist",),
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("add",),
        "selection_priority": 80,
    },
    "watchlist_remove": {
        "any_entities": ("watchlist",),
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("remove",),
        "selection_priority": 80,
    },
    "activate_bot": {
        "any_entities": ("bot",),
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("activate",),
        "selection_priority": 80,
    },
    "activate_paper_bot": {
        "any_entities": ("bot",),
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("activate",),
        "selection_required_terms": ("paper",),
        "selection_priority": 90,
    },
    "confirm_proposal": {
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("confirm",),
        "selection_priority": 100,
    },
    "execute_proposal": {
        "required_discourse_acts": ("operation_request",),
        "allowed_action_polarities": ("execute",),
        "selection_priority": 100,
    },
}


_CONTRACTS: tuple[OperationContract, ...] = (
    OperationContract("capability", FinnV2OperationRegistry.VERSION, "system", "CAPABILITY", ("wat kun je", "what can you", "capabilities"), required_scopes=("capability",), response_strategy="deterministic_template"),
    OperationContract("clarify_request", FinnV2OperationRegistry.VERSION, "system", "CLARIFICATION", (), response_strategy="clarification"),
    OperationContract("unavailable", FinnV2OperationRegistry.VERSION, "system", "UNAVAILABLE", (), response_strategy="unavailable"),
    OperationContract("explain_previous_evidence", FinnV2OperationRegistry.VERSION, "system", "EVALUATE", ("onderbouw", "evidence", "waarom"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"), model_policy="required", response_strategy="model_reasoning"),
    OperationContract("reformulate_previous_response", FinnV2OperationRegistry.VERSION, "system", "READ", ("korter", "anders formuleren", "reformuleer"), response_strategy="deterministic_structured_summary"),
    _read("read_active_asset", "asset", ("active_asset",), ("actieve asset", "welke asset"), ("asset",)),
    _gap("select_asset", "asset", "ACTION_PROPOSAL", ("selecteer asset",), "select_asset_execution_adapter_missing"),
    _read("read_watchlist", "asset", ("active_asset", "watchlist"), ("watchlist", "volglijst")),
    OperationContract("watchlist_add", FinnV2OperationRegistry.VERSION, "watchlist", "ACTION_PROPOSAL", ("voeg", "add", "watchlist"), required_inputs=("asset",), required_scopes=("active_asset", "watchlist"), proposal_type="watchlist_add", confirmation_required=True, execution_adapter="watchlist_add", idempotency_rule="user_asset_unique", postcondition="watchlist_contains_asset", response_strategy="proposal_draft", policy_class="proposal"),
    OperationContract("watchlist_remove", FinnV2OperationRegistry.VERSION, "watchlist", "ACTION_PROPOSAL", ("verwijder", "remove", "watchlist"), required_inputs=("asset",), required_scopes=("active_asset", "watchlist"), proposal_type="watchlist_remove", confirmation_required=True, execution_adapter="watchlist_remove", idempotency_rule="user_asset_absent", postcondition="watchlist_excludes_asset", response_strategy="proposal_draft", policy_class="proposal"),
    _read("read_indicator_configuration", "indicators", ("active_asset", "indicator_configuration"), ("indicator", "rsi", "vwap", "volume"), ("asset", "indicator_configuration")),
    _gap("create_indicator_configuration", "indicators", "CREATE_PROPOSAL", ("maak indicator",), "create_indicator_configuration_adapter_missing"),
    _gap("update_indicator_configuration", "indicators", "CREATE_PROPOSAL", ("wijzig indicator",), "proposal_payload_contract_missing"),
    _gap("delete_indicator_configuration", "indicators", "CREATE_PROPOSAL", ("verwijder indicator",), "delete_indicator_configuration_adapter_missing"),
    OperationContract("evaluate_indicator_configuration", FinnV2OperationRegistry.VERSION, "indicators", "EVALUATE", ("beoordeel indicator",), required_scopes=("active_asset", "indicator_configuration"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _read("read_active_setup", "setup", ("active_asset", "active_setup"), ("actieve setup", "welke setup"), ("setup", "timeframe")),
    # SetupService validates these three fields unconditionally. Timeframe and
    # score/market-condition details are useful trusted inputs, but are not
    # schema-required and must not be invented by FINN.
    OperationContract("create_setup", FinnV2OperationRegistry.VERSION, "setup", "CREATE_PROPOSAL", ("maak setup", "create setup", "setup voor"), required_inputs=("name", "symbol", "setup_type"), required_scopes=("active_asset",), optional_scopes=("profile", "preferences", "indicator_configuration", "active_setup", "linked_strategy"), model_policy="optional", response_strategy="proposal_draft", policy_class="proposal", proposal_type="create_setup", confirmation_required=True, execution_adapter="create_setup", idempotency_rule="proposal_payload_hash", postcondition="setup_created_for_user_asset"),
    OperationContract("update_setup", FinnV2OperationRegistry.VERSION, "setup", "CREATE_PROPOSAL", ("wijzig setup",), required_inputs=("setup_id", "changed_fields"), required_scopes=("active_asset", "active_setup"), proposal_type="update_setup", confirmation_required=True, execution_adapter="update_setup", idempotency_rule="proposal_payload_hash", postcondition="setup_updated_for_user"),
    _gap("delete_setup", "setup", "CREATE_PROPOSAL", ("verwijder setup",), "delete_setup_execution_adapter_missing"),
    OperationContract("evaluate_setup", FinnV2OperationRegistry.VERSION, "setup", "EVALUATE", ("beoordeel setup",), required_scopes=("active_asset", "active_setup"), optional_scopes=("indicator_configuration",), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _read("read_linked_strategy", "strategy", ("active_asset", "active_setup", "linked_strategy"), ("welke strategie", "strategie"), ("setup", "strategy")),
    _gap("create_strategy", "strategy", "CREATE_PROPOSAL", ("maak strategie",), "create_strategy_execution_adapter_missing"),
    OperationContract("update_strategy", FinnV2OperationRegistry.VERSION, "strategy", "CREATE_PROPOSAL", ("wijzig strategie",), required_inputs=("strategy_id", "changed_fields"), required_scopes=("active_asset", "active_setup", "linked_strategy"), proposal_type="update_strategy", confirmation_required=True, execution_adapter="update_strategy", idempotency_rule="proposal_payload_hash", postcondition="strategy_updated_for_user"),
    _gap("delete_strategy", "strategy", "CREATE_PROPOSAL", ("verwijder strategie",), "delete_strategy_execution_adapter_missing"),
    OperationContract("evaluate_strategy", FinnV2OperationRegistry.VERSION, "strategy", "EVALUATE", ("beoordeel strategie", "strategie past"), required_scopes=("profile", "preferences", "active_asset", "active_setup", "linked_strategy"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _read("read_linked_bot", "bot", ("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"), ("welke bot", "gekoppelde bot"), ("setup", "strategy", "bot", "bot_status")),
    _read("read_bot_status", "bot", ("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"), ("bot status", "staat hij live"), ("bot", "bot_status")),
    _gap("create_bot", "bot", "CREATE_PROPOSAL", ("maak bot",), "create_bot_execution_adapter_missing"),
    _gap("update_bot", "bot", "CREATE_PROPOSAL", ("wijzig bot",), "update_bot_execution_adapter_missing"),
    _gap("delete_bot", "bot", "CREATE_PROPOSAL", ("verwijder bot",), "delete_bot_execution_adapter_missing"),
    OperationContract("evaluate_bot", FinnV2OperationRegistry.VERSION, "bot", "EVALUATE", ("beoordeel bot", "vertrouwen bot"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    OperationContract("activate_bot", FinnV2OperationRegistry.VERSION, "bot", "ACTION_PROPOSAL", ("activeer bot",), required_inputs=("bot_id",), required_scopes=("active_asset", "market_snapshot", "active_setup", "linked_strategy", "linked_bot", "bot_status"), proposal_type="activate_live_bot", confirmation_required=True, execution_adapter="activate_live_bot", idempotency_rule="proposal_payload_hash", postcondition="live_bot_active", response_strategy="policy_denial", policy_class="high_risk_action"),
    OperationContract("activate_paper_bot", FinnV2OperationRegistry.VERSION, "bot", "ACTION_PROPOSAL", ("activeer paper bot",), required_inputs=("bot_id",), required_scopes=("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"), proposal_type="activate_paper_bot", confirmation_required=True, execution_adapter="activate_paper_bot", idempotency_rule="proposal_payload_hash", postcondition="paper_bot_active", response_strategy="proposal_draft", policy_class="paper_action"),
    _gap("deactivate_bot", "bot", "ACTION_PROPOSAL", ("deactiveer bot",), "deactivate_bot_execution_adapter_missing"),
    OperationContract("read_active_plan", FinnV2OperationRegistry.VERSION, "plan", "READ", ("mijn actieve plan", "setup strategie bot"), required_scopes=("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"), required_response_fields=("setup", "strategy", "bot", "bot_status")),
    OperationContract("evaluate_plan", FinnV2OperationRegistry.VERSION, "plan", "EVALUATE", ("belangrijkste ontbrekende", "bekijk mijn profiel", "beoordeel mijn plan"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"), model_policy="required", response_strategy="model_reasoning", policy_class="advice", required_response_fields=("observation", "evidence", "next_step")),
    _gap("read_portfolio", "portfolio", "READ", ("portfolio", "portefeuille"), "portfolio_contract_not_yet_grounded"),
    _gap("evaluate_portfolio", "portfolio", "EVALUATE", ("beoordeel portfolio",), "portfolio_contract_not_yet_grounded"),
    _gap("read_latest_report", "reports", "READ", ("laatste rapport",), "report_contract_not_yet_grounded"),
    _gap("read_review_history", "reviews", "READ", ("review geschiedenis",), "review_contract_not_yet_grounded"),
    _gap("evaluate_review_history", "reviews", "EVALUATE", ("beoordeel review",), "review_contract_not_yet_grounded"),
    OperationContract("confirm_proposal", FinnV2OperationRegistry.VERSION, "workflow", "CONFIRMATION", ("bevestig", "confirm"), required_inputs=("proposal_id",), proposal_type="confirmation", confirmation_required=True, response_strategy="execution_result", policy_class="proposal"),
    OperationContract("execute_proposal", FinnV2OperationRegistry.VERSION, "workflow", "EXECUTION", ("voer uit", "execute"), required_inputs=("proposal_id",), proposal_type="execution", confirmation_required=True, response_strategy="execution_result", policy_class="proposal"),
)
