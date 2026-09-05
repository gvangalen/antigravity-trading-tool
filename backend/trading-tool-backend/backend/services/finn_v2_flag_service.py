from __future__ import annotations

import logging
import os
from typing import Set

from backend.domain.finn_v2_contract import normalize_interaction_mode


logger = logging.getLogger(__name__)


class FinnV2FlagService:
    def _env_bool(self, name: str, default: bool) -> bool:
        return str(os.getenv(name, str(default).lower())).strip().lower() in {"1", "true", "yes", "on"}

    def _env_int(self, name: str, default: int) -> int:
        raw = str(os.getenv(name, default)).strip()
        try:
            return int(raw)
        except ValueError:
            logger.warning("FINN V2 misconfiguration: %s=%r is not an integer.", name, raw)
            return default

    def _allowed_transports(self) -> Set[str]:
        raw = os.getenv("FINN_V2_ALLOWED_TRANSPORTS", "chat,stream")
        values = {item.strip() for item in raw.split(",") if item.strip()}
        return values or {"chat", "stream"}

    def is_enabled_globally(self) -> bool:
        return self._env_bool("FINN_V2_ENABLED", True)

    def is_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_SHADOW_ENABLED", False)

    def is_canary_user(self, user_id: int) -> bool:
        raw = os.getenv("FINN_V2_CANARY_USER_IDS", "")
        parsed = {item.strip() for item in raw.split(",") if item.strip()}
        return str(user_id) in parsed

    def is_visible_for_user(self, user_id: int) -> bool:
        return self._env_bool("FINN_V2_VISIBLE_ENABLED", True)

    def is_write_blocked(self) -> bool:
        return self._env_bool("FINN_V2_WRITE_BLOCKED", True)

    def allows_transport(self, transport: str) -> bool:
        return transport in self._allowed_transports()

    def max_runs_per_minute(self) -> int:
        return self._env_int("FINN_V2_MAX_RUNS_PER_MINUTE", 20)

    def shadow_enqueue_timeout_ms(self) -> int:
        return self._env_int("FINN_V2_SHADOW_ENQUEUE_TIMEOUT_MS", 100)

    def direct_dispatch_timeout_ms(self) -> int:
        """Bound synchronous broker handoff without penalizing cold pools."""
        return max(500, min(10_000, self._env_int("FINN_V2_DIRECT_DISPATCH_TIMEOUT_MS", 5_000)))

    def message_retention_days(self) -> int:
        return self._env_int("FINN_V2_MESSAGE_RETENTION_DAYS", 30)

    def trace_retention_days(self) -> int:
        return self._env_int("FINN_V2_TRACE_RETENTION_DAYS", 90)

    def is_tool_registry_enabled(self) -> bool:
        return self._env_bool("FINN_V2_TOOL_REGISTRY_ENABLED", True)

    def is_tool_registry_readonly(self) -> bool:
        return self._env_bool("FINN_V2_TOOL_REGISTRY_READONLY", True)

    def is_tool_call_logging_enabled(self) -> bool:
        return self._env_bool("FINN_V2_TOOL_CALL_LOGGING_ENABLED", True)

    def tool_result_retention_days(self) -> int:
        return self._env_int("FINN_V2_TOOL_RESULT_RETENTION_DAYS", 30)

    def tool_metadata_retention_days(self) -> int:
        return self._env_int("FINN_V2_TOOL_METADATA_RETENTION_DAYS", 90)

    def is_tool_shadow_execution_enabled(self) -> bool:
        return self._env_bool("FINN_V2_TOOL_SHADOW_EXECUTION_ENABLED", False)

    def is_tool_shadow_canary_user(self, user_id: int) -> bool:
        raw = os.getenv("FINN_V2_TOOL_SHADOW_CANARY_USER_IDS", "")
        parsed = {item.strip() for item in raw.split(",") if item.strip()}
        return str(user_id) in parsed

    def is_state_assembly_enabled(self) -> bool:
        return self._env_bool("FINN_V2_STATE_ASSEMBLY_ENABLED", True)

    def is_state_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_STATE_SHADOW_ENABLED", False)

    def is_orchestrator_enabled(self) -> bool:
        return self._env_bool("FINN_V2_ORCHESTRATOR_ENABLED", True)

    def is_orchestrator_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_ORCHESTRATOR_SHADOW_ENABLED", True)

    def is_policy_engine_enabled(self) -> bool:
        return self._env_bool("FINN_V2_POLICY_ENGINE_ENABLED", True)

    def is_proposals_enabled(self) -> bool:
        return self._env_bool("FINN_V2_PROPOSALS_ENABLED", True)

    def is_confirmations_enabled(self) -> bool:
        return self._env_bool("FINN_V2_CONFIRMATIONS_ENABLED", True)

    def is_execution_gate_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTION_GATE_ENABLED", True)

    def is_live_actions_enabled(self) -> bool:
        return self._env_bool("FINN_V2_LIVE_ACTIONS_ENABLED", False)

    def is_paper_actions_enabled(self) -> bool:
        return self._env_bool("FINN_V2_PAPER_ACTIONS_ENABLED", False)

    def is_action_kill_switch_enabled(self) -> bool:
        return self._env_bool("FINN_V2_ACTION_KILL_SWITCH", True)

    def require_step_up_for_live(self) -> bool:
        return self._env_bool("FINN_V2_REQUIRE_STEP_UP_FOR_LIVE", True)

    def proposal_ttl_seconds(self) -> int:
        return self._env_int("FINN_V2_PROPOSAL_TTL_SECONDS", 900)

    def is_reasoning_enabled(self) -> bool:
        return self._env_bool("FINN_V2_REASONING_ENABLED", True)

    def is_reasoning_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_REASONING_SHADOW_ENABLED", True)

    def reasoning_model_override(self) -> str | None:
        value = str(os.getenv("FINN_V2_REASONING_MODEL", "")).strip()
        return value or None

    def reasoning_timeout_seconds(self) -> int:
        return self._env_int("FINN_V2_REASONING_TIMEOUT_SECONDS", 45)

    def lifecycle_deadline_seconds(self) -> int:
        """Bound worker ownership before a visible request exceeds its SLA."""
        return max(5, min(15, self._env_int("FINN_V2_LIFECYCLE_DEADLINE_SECONDS", 14)))

    def selector_phase_deadline_seconds(self) -> int:
        # The measured structured Responses call can validly take just over
        # ten seconds. Keep its own bounded phase below the overall runtime,
        # while reserving terminal persistence before post-selection work.
        return max(5, min(25, self._env_int("FINN_V2_SELECTOR_PHASE_DEADLINE_SECONDS", 20)))

    def selector_provider_timeout_seconds(self) -> int:
        """Reserve time to persist a successful structured selection."""
        return max(3, self.selector_phase_deadline_seconds() - self.terminal_persistence_reserve_seconds())

    def terminal_persistence_reserve_seconds(self) -> int:
        return max(1, min(5, self._env_int("FINN_V2_TERMINAL_PERSISTENCE_RESERVE_SECONDS", 2)))

    def visible_request_timeout_seconds(self) -> int:
        return max(1, min(20, self._env_int("FINN_V2_VISIBLE_REQUEST_TIMEOUT_SECONDS", 20)))

    def reasoning_max_output_tokens(self) -> int:
        return self._env_int("FINN_V2_REASONING_MAX_OUTPUT_TOKENS", 1800)

    def reasoning_max_retries(self) -> int:
        return max(0, min(1, self._env_int("FINN_V2_REASONING_MAX_RETRIES", 1)))

    def reasoning_effort(self) -> str:
        value = str(os.getenv("FINN_V2_REASONING_EFFORT", "medium")).strip().lower()
        return value if value in {"low", "medium", "high"} else "medium"

    def reasoning_max_evidence_items(self) -> int:
        return self._env_int("FINN_V2_REASONING_MAX_EVIDENCE_ITEMS", 30)

    def reasoning_max_context_bytes(self) -> int:
        return self._env_int("FINN_V2_REASONING_MAX_CONTEXT_BYTES", 131072)

    def evidence_payload_retention_days(self) -> int:
        return self._env_int("FINN_V2_EVIDENCE_PAYLOAD_RETENTION_DAYS", 30)

    def state_payload_retention_days(self) -> int:
        return self._env_int("FINN_V2_STATE_PAYLOAD_RETENTION_DAYS", 30)

    def validation_payload_retention_days(self) -> int:
        return self._env_int("FINN_V2_VALIDATION_PAYLOAD_RETENTION_DAYS", 90)

    def evidence_max_payload_bytes(self) -> int:
        return self._env_int("FINN_V2_EVIDENCE_MAX_PAYLOAD_BYTES", 65536)

    def state_max_payload_bytes(self) -> int:
        return self._env_int("FINN_V2_STATE_MAX_PAYLOAD_BYTES", 262144)

    def should_run_block3_shadow(self, user_id: int) -> bool:
        return (
            self.is_enabled_globally()
            and self.is_tool_registry_enabled()
            and self.is_state_assembly_enabled()
        )

    def should_run_block4_shadow(self, user_id: int) -> bool:
        return (
            self.should_run_block3_shadow(user_id)
            and self.is_orchestrator_enabled()
            and self.is_orchestrator_shadow_enabled()
        )

    def should_run_block5_shadow(self, user_id: int) -> bool:
        return self.should_run_block4_shadow(user_id) and self.is_policy_engine_enabled()

    def should_run_block6_shadow(self, user_id: int) -> bool:
        return self.should_run_block5_shadow(user_id) and self.is_reasoning_enabled() and self.is_reasoning_shadow_enabled()

    def is_response_verifier_enabled(self) -> bool:
        return self._env_bool("FINN_V2_RESPONSE_VERIFIER_ENABLED", True)

    def is_response_delivery_enabled(self) -> bool:
        return self._env_bool("FINN_V2_RESPONSE_DELIVERY_ENABLED", True)

    def is_response_repair_enabled(self) -> bool:
        return self._env_bool("FINN_V2_RESPONSE_REPAIR_ENABLED", True)

    def response_max_repair_attempts(self) -> int:
        return max(0, min(1, self._env_int("FINN_V2_RESPONSE_MAX_REPAIR_ATTEMPTS", 1)))

    def is_semantic_verifier_enabled(self) -> bool:
        return self._env_bool("FINN_V2_SEMANTIC_VERIFIER_ENABLED", False)

    def semantic_verifier_model(self) -> str | None:
        value = str(os.getenv("FINN_V2_SEMANTIC_VERIFIER_MODEL", "")).strip()
        return value or None

    def semantic_verifier_required_modes(self) -> Set[str]:
        raw = os.getenv("FINN_V2_SEMANTIC_VERIFIER_REQUIRED_MODES", "EVALUATE,CREATE_PROPOSAL,ACTION_PROPOSAL")
        parsed = {normalize_interaction_mode(item.strip().upper()) for item in raw.split(",") if item.strip()}
        return parsed or {"EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL"}

    def semantic_verifier_timeout_seconds(self) -> int:
        return self._env_int("FINN_V2_SEMANTIC_VERIFIER_TIMEOUT_SECONDS", 30)

    def semantic_verifier_max_retries(self) -> int:
        return max(0, min(0, self._env_int("FINN_V2_SEMANTIC_VERIFIER_MAX_RETRIES", 0)))

    def should_run_block7_shadow(self, user_id: int) -> bool:
        return (
            self.should_run_block6_shadow(user_id)
            and self.is_response_verifier_enabled()
            and self.is_response_delivery_enabled()
        )

    def runtime_mode(self) -> str:
        value = str(os.getenv("FINN_V2_RUNTIME_MODE", "v2_only")).strip()
        return value if value in {"v2_only"} else "v2_only"

    def is_shadow_compare_enabled(self) -> bool:
        return self._env_bool("FINN_V2_SHADOW_COMPARE_ENABLED", False)

    def is_golden_evals_enabled(self) -> bool:
        return self._env_bool("FINN_V2_GOLDEN_EVALS_ENABLED", False)

    def is_release_gates_enabled(self) -> bool:
        return self._env_bool("FINN_V2_RELEASE_GATES_ENABLED", False)

    def canary_user_ids(self) -> Set[str]:
        raw = os.getenv("FINN_V2_CANARY_USER_IDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def canary_percent(self) -> int:
        return max(0, min(100, self._env_int("FINN_V2_CANARY_PERCENT", 0)))

    def canary_allowed_modes(self) -> Set[str]:
        raw = os.getenv("FINN_V2_CANARY_ALLOWED_MODES", "READ,EVALUATE")
        values = {normalize_interaction_mode(item.strip().upper()) for item in raw.split(",") if item.strip()}
        return values or {"READ", "EVALUATE"}

    def is_v1_fallback_enabled(self) -> bool:
        return self._env_bool("FINN_V2_V1_FALLBACK_ENABLED", False)

    def is_post_cutover_kill_switch_enabled(self) -> bool:
        return self._env_bool("FINN_V2_POST_CUTOVER_KILL_SWITCH", False)

    def visible_request_timeout_seconds(self, interaction_mode: str | None = None) -> int:
        default_timeout = self._env_int("FINN_V2_VISIBLE_REQUEST_TIMEOUT_SECONDS", 20)
        mode = str(interaction_mode or "").strip().upper()
        if mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
            return self._env_int(
                "FINN_V2_VISIBLE_REQUEST_TIMEOUT_MUTATION_SECONDS",
                max(default_timeout, 45),
            )
        if mode in {"CAPABILITY", "UNAVAILABLE", "CLARIFICATION"}:
            return self._env_int(
                "FINN_V2_VISIBLE_REQUEST_TIMEOUT_LIGHT_SECONDS",
                min(default_timeout, 10),
            )
        return default_timeout

    def is_visible_proposals_enabled(self) -> bool:
        return self._env_bool("FINN_V2_VISIBLE_PROPOSALS_ENABLED", True)

    def is_confirmation_routes_enabled(self) -> bool:
        return self._env_bool("FINN_V2_CONFIRMATION_ROUTES_ENABLED", True)

    def is_action_execution_enabled(self) -> bool:
        return self._env_bool("FINN_V2_ACTION_EXECUTION_ENABLED", True)

    def execute_indicator_changes_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_INDICATOR_CHANGES", False)

    def execute_setup_changes_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_SETUP_CHANGES", False)

    def execute_strategy_changes_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_STRATEGY_CHANGES", False)

    def execute_watchlist_changes_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_WATCHLIST_CHANGES", True)

    def execute_trade_plan_changes_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_TRADE_PLAN_CHANGES", False)

    def execute_paper_bot_activation_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_PAPER_BOT_ACTIVATION", False)

    def execute_live_bot_activation_enabled(self) -> bool:
        return self._env_bool("FINN_V2_EXECUTE_LIVE_BOT_ACTIVATION", False)

    def _is_safe_readonly_config(self) -> bool:
        if not self.is_write_blocked():
            logger.warning("FINN V2 disabled because FINN_V2_WRITE_BLOCKED is false.")
            return False
        if self._env_int("FINN_V2_MAX_EXECUTES_PER_MINUTE", 0) != 0:
            logger.warning("FINN V2 disabled because FINN_V2_MAX_EXECUTES_PER_MINUTE is not zero.")
            return False
        if not {"chat", "stream"}.issuperset(self._allowed_transports()):
            logger.warning("FINN V2 disabled because FINN_V2_ALLOWED_TRANSPORTS contains unsupported values.")
            return False
        return True

    def resolve_mode(self, user_id: int) -> str:
        if not self.is_enabled_globally():
            return "disabled"
        if not self._is_safe_readonly_config():
            return "disabled"
        return "visible_runtime"
