from __future__ import annotations

import logging
import os
from typing import Set


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
        return self._env_bool("FINN_V2_ENABLED", False)

    def is_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_SHADOW_ENABLED", False)

    def is_canary_user(self, user_id: int) -> bool:
        raw = os.getenv("FINN_V2_CANARY_USER_IDS", "")
        parsed = {item.strip() for item in raw.split(",") if item.strip()}
        return str(user_id) in parsed

    def is_visible_for_user(self, user_id: int) -> bool:
        return self._env_bool("FINN_V2_VISIBLE_ENABLED", False) and self.is_canary_user(user_id)

    def is_write_blocked(self) -> bool:
        return self._env_bool("FINN_V2_WRITE_BLOCKED", True)

    def allows_transport(self, transport: str) -> bool:
        return transport in self._allowed_transports()

    def max_runs_per_minute(self) -> int:
        return self._env_int("FINN_V2_MAX_RUNS_PER_MINUTE", 20)

    def shadow_enqueue_timeout_ms(self) -> int:
        return self._env_int("FINN_V2_SHADOW_ENQUEUE_TIMEOUT_MS", 100)

    def message_retention_days(self) -> int:
        return self._env_int("FINN_V2_MESSAGE_RETENTION_DAYS", 30)

    def trace_retention_days(self) -> int:
        return self._env_int("FINN_V2_TRACE_RETENTION_DAYS", 90)

    def is_tool_registry_enabled(self) -> bool:
        return self._env_bool("FINN_V2_TOOL_REGISTRY_ENABLED", False)

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
        return self._env_bool("FINN_V2_STATE_ASSEMBLY_ENABLED", False)

    def is_state_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_STATE_SHADOW_ENABLED", False)

    def is_orchestrator_enabled(self) -> bool:
        return self._env_bool("FINN_V2_ORCHESTRATOR_ENABLED", True)

    def is_orchestrator_shadow_enabled(self) -> bool:
        return self._env_bool("FINN_V2_ORCHESTRATOR_SHADOW_ENABLED", True)

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
            and self.is_shadow_enabled()
            and self.is_tool_registry_enabled()
            and self.is_tool_shadow_execution_enabled()
            and self.is_state_assembly_enabled()
            and self.is_state_shadow_enabled()
            and self.is_tool_shadow_canary_user(user_id)
        )

    def should_run_block4_shadow(self, user_id: int) -> bool:
        return (
            self.should_run_block3_shadow(user_id)
            and self.is_orchestrator_enabled()
            and self.is_orchestrator_shadow_enabled()
        )

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
        if self.is_visible_for_user(user_id):
            return "visible_readonly"
        if self.is_shadow_enabled():
            return "shadow"
        return "disabled"
