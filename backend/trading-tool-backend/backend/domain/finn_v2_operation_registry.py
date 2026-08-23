"""Canonical FINN V2 operation contracts.

This module deliberately owns the operation decisions that used to be spread
across request analysis, domain requirements, planning and policy.  Runtime
services may consume a contract but must not add scopes, tools or write rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Mapping, Optional

from backend.domain.finn_v2_contract import INFORMATION_SCOPE_ORDER, primary_tool_for_information_scope


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
    required_inputs: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    optional_scopes: tuple[str, ...] = ()
    model_policy: str = "never"  # never | optional | required
    response_strategy: str = "deterministic_structured_summary"
    policy_class: str = "read"
    proposal_type: Optional[str] = None
    confirmation_required: bool = False
    execution_adapter: Optional[str] = None
    idempotency_rule: Optional[str] = None
    postcondition: Optional[str] = None
    verifier_rules: tuple[str, ...] = ("grounded", "mode_pure")
    allowed_terminal_outcomes: tuple[str, ...] = ("completed", "clarification_required", "unavailable")
    supported: bool = True
    capability_gap: Optional[str] = None

    def __post_init__(self) -> None:
        if self.mode not in {
            "CAPABILITY", "READ", "EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL",
            "CLARIFICATION", "CONFIRMATION", "EXECUTION", "UNAVAILABLE",
        }:
            raise FinnV2OperationContractError(f"invalid_mode:{self.operation_id}:{self.mode}")
        if set(self.required_scopes).intersection(self.optional_scopes):
            raise FinnV2OperationContractError(f"scope_overlap:{self.operation_id}")
        unknown = set(self.required_scopes + self.optional_scopes).difference(INFORMATION_SCOPE_ORDER)
        if unknown:
            raise FinnV2OperationContractError(f"unknown_scope:{self.operation_id}:{sorted(unknown)}")
        if self.model_policy not in {"never", "optional", "required"}:
            raise FinnV2OperationContractError(f"invalid_model_policy:{self.operation_id}")
        write = self.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}
        if write and self.supported and (not self.proposal_type or not self.confirmation_required):
            raise FinnV2OperationContractError(f"write_contract_incomplete:{self.operation_id}")
        if self.execution_adapter and not self.idempotency_rule:
            raise FinnV2OperationContractError(f"adapter_without_idempotency:{self.operation_id}")

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(
            primary_tool_for_information_scope(scope)
            for scope in self.required_scopes
            if scope != "capability"
        )


class FinnV2OperationRegistry:
    VERSION = "2026-08-23.operation-contracts.v1"

    def __init__(self) -> None:
        self._contracts = {contract.operation_id: contract for contract in _CONTRACTS}
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

    def resolve_alias(self, text: str) -> Optional[OperationContract]:
        normalized = str(text or "").casefold()
        matches = [contract for contract in self._contracts.values() if any(alias in normalized for alias in contract.aliases)]
        return max(matches, key=lambda item: len(max(item.aliases, key=len))) if matches else None

    def _validate_manifest(self) -> None:
        if len(self._contracts) != len(_CONTRACTS):
            raise FinnV2OperationContractError("duplicate_operation_id")
        for contract in self._contracts.values():
            if contract.supported:
                for scope in contract.required_scopes:
                    if scope != "capability":
                        primary_tool_for_information_scope(scope)


def _read(operation_id: str, domain: str, scopes: tuple[str, ...], aliases: tuple[str, ...]) -> OperationContract:
    return OperationContract(operation_id, FinnV2OperationRegistry.VERSION, domain, "READ", aliases, required_scopes=scopes)


def _gap(operation_id: str, domain: str, mode: str, aliases: tuple[str, ...], reason: str) -> OperationContract:
    return OperationContract(operation_id, FinnV2OperationRegistry.VERSION, domain, mode, aliases, supported=False, capability_gap=reason)


_CONTRACTS: tuple[OperationContract, ...] = (
    OperationContract("capability", FinnV2OperationRegistry.VERSION, "system", "CAPABILITY", ("wat kun je", "what can you", "capabilities"), required_scopes=("capability",), response_strategy="deterministic_template"),
    OperationContract("clarify_request", FinnV2OperationRegistry.VERSION, "system", "CLARIFICATION", (), response_strategy="clarification"),
    OperationContract("unavailable", FinnV2OperationRegistry.VERSION, "system", "UNAVAILABLE", (), response_strategy="unavailable"),
    OperationContract("explain_previous_evidence", FinnV2OperationRegistry.VERSION, "system", "EVALUATE", ("onderbouw", "evidence", "waarom"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"), model_policy="required", response_strategy="model_reasoning"),
    OperationContract("reformulate_previous_response", FinnV2OperationRegistry.VERSION, "system", "READ", ("korter", "anders formuleren", "reformuleer"), response_strategy="deterministic_structured_summary"),
    _read("read_active_asset", "asset", ("active_asset",), ("actieve asset", "welke asset")),
    _gap("select_asset", "asset", "ACTION_PROPOSAL", ("selecteer asset",), "select_asset_execution_adapter_missing"),
    _read("read_watchlist", "asset", ("active_asset", "watchlist"), ("watchlist", "volglijst")),
    OperationContract("watchlist_add", FinnV2OperationRegistry.VERSION, "asset", "ACTION_PROPOSAL", ("voeg", "add", "watchlist"), required_inputs=("asset",), required_scopes=("active_asset", "watchlist"), proposal_type="watchlist_add", confirmation_required=True, execution_adapter="watchlist_add", idempotency_rule="user_asset_unique", postcondition="watchlist_contains_asset", response_strategy="proposal_draft", policy_class="proposal"),
    OperationContract("watchlist_remove", FinnV2OperationRegistry.VERSION, "asset", "ACTION_PROPOSAL", ("verwijder", "remove", "watchlist"), required_inputs=("asset",), required_scopes=("active_asset", "watchlist"), proposal_type="watchlist_remove", confirmation_required=True, execution_adapter="watchlist_remove", idempotency_rule="user_asset_absent", postcondition="watchlist_excludes_asset", response_strategy="proposal_draft", policy_class="proposal"),
    _read("read_indicator_configuration", "indicators", ("active_asset", "indicator_configuration"), ("indicator", "rsi", "vwap", "volume")),
    _gap("create_indicator_configuration", "indicators", "CREATE_PROPOSAL", ("maak indicator",), "create_indicator_configuration_adapter_missing"),
    _gap("update_indicator_configuration", "indicators", "CREATE_PROPOSAL", ("wijzig indicator",), "proposal_payload_contract_missing"),
    _gap("delete_indicator_configuration", "indicators", "CREATE_PROPOSAL", ("verwijder indicator",), "delete_indicator_configuration_adapter_missing"),
    OperationContract("evaluate_indicator_configuration", FinnV2OperationRegistry.VERSION, "indicators", "EVALUATE", ("beoordeel indicator",), required_scopes=("active_asset", "indicator_configuration"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _read("read_active_setup", "setup", ("active_asset", "active_setup"), ("actieve setup", "welke setup")),
    # SetupService validates these three fields unconditionally. Timeframe and
    # score/market-condition details are useful trusted inputs, but are not
    # schema-required and must not be invented by FINN.
    OperationContract("create_setup", FinnV2OperationRegistry.VERSION, "setup", "CREATE_PROPOSAL", ("maak setup", "create setup", "setup voor"), required_inputs=("name", "symbol", "setup_type"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration"), optional_scopes=("active_setup", "linked_strategy"), model_policy="optional", response_strategy="proposal_draft", policy_class="proposal", proposal_type="create_setup", confirmation_required=True, execution_adapter="create_setup", idempotency_rule="proposal_payload_hash", postcondition="setup_created_for_user_asset"),
    OperationContract("update_setup", FinnV2OperationRegistry.VERSION, "setup", "CREATE_PROPOSAL", ("wijzig setup",), required_inputs=("setup_id", "changed_fields"), required_scopes=("active_asset", "active_setup"), proposal_type="update_setup", confirmation_required=True, execution_adapter="update_setup", idempotency_rule="proposal_payload_hash", postcondition="setup_updated_for_user"),
    _gap("delete_setup", "setup", "CREATE_PROPOSAL", ("verwijder setup",), "delete_setup_execution_adapter_missing"),
    OperationContract("evaluate_setup", FinnV2OperationRegistry.VERSION, "setup", "EVALUATE", ("beoordeel setup",), required_scopes=("active_asset", "active_setup"), optional_scopes=("indicator_configuration",), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _read("read_linked_strategy", "strategy", ("active_asset", "active_setup", "linked_strategy"), ("welke strategie", "strategie")),
    _gap("create_strategy", "strategy", "CREATE_PROPOSAL", ("maak strategie",), "create_strategy_execution_adapter_missing"),
    OperationContract("update_strategy", FinnV2OperationRegistry.VERSION, "strategy", "CREATE_PROPOSAL", ("wijzig strategie",), required_inputs=("strategy_id", "changed_fields"), required_scopes=("active_asset", "active_setup", "linked_strategy"), proposal_type="update_strategy", confirmation_required=True, execution_adapter="update_strategy", idempotency_rule="proposal_payload_hash", postcondition="strategy_updated_for_user"),
    _gap("delete_strategy", "strategy", "CREATE_PROPOSAL", ("verwijder strategie",), "delete_strategy_execution_adapter_missing"),
    OperationContract("evaluate_strategy", FinnV2OperationRegistry.VERSION, "strategy", "EVALUATE", ("beoordeel strategie", "strategie past"), required_scopes=("profile", "preferences", "active_asset", "active_setup", "linked_strategy"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _read("read_linked_bot", "bot", ("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"), ("welke bot", "gekoppelde bot")),
    _read("read_bot_status", "bot", ("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"), ("bot status", "staat hij live")),
    _gap("create_bot", "bot", "CREATE_PROPOSAL", ("maak bot",), "create_bot_execution_adapter_missing"),
    _gap("update_bot", "bot", "CREATE_PROPOSAL", ("wijzig bot",), "update_bot_execution_adapter_missing"),
    _gap("delete_bot", "bot", "CREATE_PROPOSAL", ("verwijder bot",), "delete_bot_execution_adapter_missing"),
    OperationContract("evaluate_bot", FinnV2OperationRegistry.VERSION, "bot", "EVALUATE", ("beoordeel bot", "vertrouwen bot"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    OperationContract("activate_bot", FinnV2OperationRegistry.VERSION, "bot", "ACTION_PROPOSAL", ("activeer bot",), required_inputs=("bot_id",), required_scopes=("active_asset", "market_snapshot", "active_setup", "linked_strategy", "linked_bot", "bot_status"), proposal_type="activate_live_bot", confirmation_required=True, execution_adapter="activate_live_bot", idempotency_rule="proposal_payload_hash", postcondition="live_bot_active", response_strategy="policy_denial", policy_class="high_risk_action"),
    _gap("deactivate_bot", "bot", "ACTION_PROPOSAL", ("deactiveer bot",), "deactivate_bot_execution_adapter_missing"),
    OperationContract("read_active_plan", FinnV2OperationRegistry.VERSION, "plan", "READ", ("mijn actieve plan", "setup strategie bot"), required_scopes=("active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status")),
    OperationContract("evaluate_plan", FinnV2OperationRegistry.VERSION, "plan", "EVALUATE", ("belangrijkste ontbrekende", "bekijk mijn profiel", "beoordeel mijn plan"), required_scopes=("profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"), model_policy="required", response_strategy="model_reasoning", policy_class="advice"),
    _gap("read_portfolio", "portfolio", "READ", ("portfolio", "portefeuille"), "portfolio_contract_not_yet_grounded"),
    _gap("evaluate_portfolio", "portfolio", "EVALUATE", ("beoordeel portfolio",), "portfolio_contract_not_yet_grounded"),
    _gap("read_latest_report", "reports", "READ", ("laatste rapport",), "report_contract_not_yet_grounded"),
    _gap("read_review_history", "reviews", "READ", ("review geschiedenis",), "review_contract_not_yet_grounded"),
    _gap("evaluate_review_history", "reviews", "EVALUATE", ("beoordeel review",), "review_contract_not_yet_grounded"),
    OperationContract("confirm_proposal", FinnV2OperationRegistry.VERSION, "workflow", "CONFIRMATION", ("bevestig", "confirm"), required_inputs=("proposal_id",), proposal_type="confirmation", confirmation_required=True, response_strategy="execution_result", policy_class="proposal"),
    OperationContract("execute_proposal", FinnV2OperationRegistry.VERSION, "workflow", "EXECUTION", ("voer uit", "execute"), required_inputs=("proposal_id",), proposal_type="execution", confirmation_required=True, response_strategy="execution_result", policy_class="proposal"),
)
