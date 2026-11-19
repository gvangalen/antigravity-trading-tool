from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Conversation
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin
from backend.domain.finn_v2_runtime_contract import RuntimeContractConflictError


class FinnV2ConversationRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id_for_user(
        self, conversation_id: str, user_id: int, *, for_update: bool = False
    ) -> Optional[FinnV2Conversation]:
        statement = select(FinnV2Conversation).where(
                FinnV2Conversation.id == conversation_id,
                FinnV2Conversation.user_id == user_id,
            )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_by_session_id_for_user(self, session_id: str, user_id: int) -> Optional[FinnV2Conversation]:
        """Resolve only a stable composer session belonging to this user."""
        result = await self.session.execute(
            select(FinnV2Conversation).where(
                FinnV2Conversation.user_id == user_id,
                FinnV2Conversation.context_json["session_id"].astext == session_id,
            )
        )
        return result.scalars().first()

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: int,
        title: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> FinnV2Conversation:
        now = datetime.now(timezone.utc)
        row = FinnV2Conversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            status="active",
            created_at=now,
            updated_at=now,
            context_json=dict(context or {}),
        )
        self.session.add(row)
        await self._flush_with_rollback(operation="create", entity_type="FinnV2Conversation")
        return row

    async def set_last_run(self, *, conversation_id: str, user_id: int, run_id: str) -> None:
        row = await self.get_by_id_for_user(conversation_id, user_id)
        if row is None:
            return
        row.last_run_id = run_id
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(operation="update_last_run", entity_type="FinnV2Conversation", run_id=run_id)

    async def get_context(self, *, conversation_id: str, user_id: int) -> Dict[str, Any]:
        row = await self.get_by_id_for_user(conversation_id, user_id)
        return dict(row.context_json or {}) if row is not None else {}

    async def register_setup_strategy_score_task(
        self, *, conversation_id: str, user_id: int, run_id: str, message: str,
    ) -> None:
        from backend.services.finn_v2_task_chain_service import STATE_KEY, requested_task

        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None:
            return
        context = dict(row.context_json or {})
        current = dict(context.get(STATE_KEY) or {})
        requested = requested_task(message)
        # A clarification of the first setup step must not narrow an already
        # requested setup -> strategy -> score task. A new asset, an explicit
        # setup-only instruction, or a finished task still starts fresh.
        clarifies_combined_setup = (
            current.get("status") == "in_progress"
            and current.get("pending_step") == "setup"
            and current.get("requested_results") == ["setup", "strategy", "score"]
            and requested is not None
            and requested.get("requested_results") == ["setup"]
            and requested.get("asset") == current.get("asset")
            and "alleen" not in str(message or "").casefold()
        )
        if current.get("status") == "in_progress" and str(message or "").strip().lower() in {
            "stop", "annuleer", "annuleren", "cancel", "stop deze opdracht",
        }:
            current.update(status="cancelled", pending_step=None,
                           pending_question=None, pending_action=None)
        elif requested and (not current or current.get("status") in {"completed", "cancelled"}
                            or (requested.get("asset") and current.get("asset")
                                and requested["asset"] != current["asset"])
                            or (not current.get("completed_steps") and not clarifies_combined_setup)):
            current = requested
        elif current.get("status") != "in_progress":
            return
        current["expected_run_id"] = run_id
        context[STATE_KEY] = current
        row.context_json = context
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="register_setup_strategy_score_task",
            entity_type="FinnV2Conversation", run_id=run_id,
        )

    async def record_setup_strategy_score_open_step(
        self, *, conversation_id: str, user_id: int, run_id: str,
        question: str | None = None, proposal_id: str | None = None,
    ) -> None:
        from backend.services.finn_v2_task_chain_service import STATE_KEY

        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None:
            return
        context = dict(row.context_json or {})
        task = dict(context.get(STATE_KEY) or {})
        if task.get("status") != "in_progress" or task.get("expected_run_id") != run_id:
            return
        task["pending_question"] = question
        task["pending_action"] = {"proposal_id": proposal_id} if proposal_id else None
        context[STATE_KEY] = task
        row.context_json = context
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="record_setup_strategy_score_open_step",
            entity_type="FinnV2Conversation", run_id=run_id,
        )

    async def record_setup_strategy_score_read(
        self, *, conversation_id: str, user_id: int, run_id: str,
        tool_trace: list[dict[str, Any]],
    ) -> None:
        from backend.services.finn_v2_task_chain_service import STATE_KEY, score_from_trace

        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None:
            return
        context = dict(row.context_json or {})
        task = dict(context.get(STATE_KEY) or {})
        if (task.get("status") != "in_progress" or task.get("pending_step") != "score"
                or task.get("expected_run_id") != run_id):
            return
        score = score_from_trace(task, tool_trace)
        if score is None:
            return
        if score["available"]:
            completed = dict(task.get("completed_steps") or {})
            completed["score"] = {**score, "run_id": run_id}
            task["completed_steps"] = completed
            task["pending_step"] = None
            task["status"] = "completed"
            task.pop("blocked_reason", None)
        else:
            task["blocked_reason"] = score["reason"]
        context[STATE_KEY] = task
        row.context_json = context
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="record_setup_strategy_score_read",
            entity_type="FinnV2Conversation", run_id=run_id,
        )

    async def update_context(self, *, conversation_id: str, user_id: int, context: Dict[str, Any]) -> None:
        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None:
            return
        current = dict(row.context_json or {})
        updated = dict(context)
        # Worker projections may have started before a confirmation completed.
        # Never let such a stale snapshot erase verified task progress.
        from backend.services.finn_v2_task_chain_service import STATE_KEY

        if current.get(STATE_KEY):
            updated[STATE_KEY] = current[STATE_KEY]
        # A run cancellation is a durable cursor boundary. A caller using a
        # pre-cancel context snapshot must not erase it by replacing JSON.
        if current.get("cancelled_proposal_run_id"):
            updated["cancelled_proposal_run_id"] = current["cancelled_proposal_run_id"]
            if dict(updated.get("responses_cursor") or {}).get("run_id") == current["cancelled_proposal_run_id"]:
                updated.pop("responses_cursor", None)
        if current.get("cancelled_proposal_id"):
            cancelled_id = current["cancelled_proposal_id"]
            updated["cancelled_proposal_id"] = cancelled_id
            if dict(updated.get("proposal_revision") or {}).get("proposal_id") == cancelled_id:
                updated.pop("proposal_revision", None)
            if dict(updated.get("active_guided_operation") or {}).get("open_proposal_id") == cancelled_id:
                updated.pop("active_guided_operation", None)
                updated.pop("operation_state", None)
        row.context_json = updated
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="update_context",
            entity_type="FinnV2Conversation",
            run_id=row.last_run_id,
        )

    async def set_selected_feed_event(
        self, *, conversation_id: str, user_id: int, run_id: str,
        feed_event: Dict[str, Any],
    ) -> None:
        """Persist an explicit feed selection across direct Responses reads."""
        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None or row.last_run_id != run_id:
            raise RuntimeContractConflictError("feed_selection_stale_or_unowned")
        previous = dict(row.context_json or {})
        # A new feed selection replaces prior plan lineage. Keep only the
        # composer identity; the next successful read writes its own cursor.
        row.context_json = {
            **({"session_id": previous["session_id"]} if previous.get("session_id") else {}),
            **({"cancelled_proposal_run_id": previous["cancelled_proposal_run_id"]}
               if previous.get("cancelled_proposal_run_id") else {}),
            **({"cancelled_proposal_id": previous["cancelled_proposal_id"]}
               if previous.get("cancelled_proposal_id") else {}),
            "feed_event": dict(feed_event),
        }
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="set_selected_feed_event",
            entity_type="FinnV2Conversation",
            run_id=run_id,
        )

    async def set_responses_cursor(
        self, *, conversation_id: str, user_id: int, run_id: str, response_id: str,
        locale: str | None = None,
    ) -> None:
        """Advance continuity only for the current owner-scoped conversation turn."""
        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None or row.last_run_id != run_id or not response_id:
            raise RuntimeContractConflictError("responses_cursor_stale_or_unowned")
        context = dict(row.context_json or {})
        if context.get("cancelled_proposal_run_id") == run_id:
            raise RuntimeContractConflictError("responses_cursor_cancelled_proposal")
        context["responses_cursor"] = {
            "run_id": run_id, "response_id": response_id,
            **({"locale": locale} if locale in {"nl", "en", "de"} else {}),
        }
        row.context_json = context
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="set_responses_cursor", entity_type="FinnV2Conversation", run_id=run_id,
        )

    async def clear_cancelled_proposal_continuation(
        self, *, conversation_id: str, user_id: int, run_id: str, proposal_id: str,
    ) -> bool:
        """Retire only the canceled card's still-current conversation cursor."""
        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None or row.last_run_id != run_id:
            return False
        context = dict(row.context_json or {})
        cursor = dict(context.get("responses_cursor") or {})
        if cursor.get("run_id") == run_id:
            context.pop("responses_cursor", None)
        context["cancelled_proposal_run_id"] = run_id
        context["cancelled_proposal_id"] = proposal_id
        revision = dict(context.get("proposal_revision") or {})
        if revision.get("proposal_id") == proposal_id:
            context.pop("proposal_revision", None)
        guided = dict(context.get("active_guided_operation") or {})
        if guided.get("open_proposal_id") == proposal_id:
            context.pop("active_guided_operation", None)
            context.pop("operation_state", None)
        row.context_json = context
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="clear_cancelled_proposal_continuation",
            entity_type="FinnV2Conversation", run_id=run_id,
        )
        return True

    async def record_verified_action_result(
        self,
        *,
        conversation_id: str,
        user_id: int,
        action_result: Dict[str, Any],
        active_target: Dict[str, Any],
        contract_revision: int,
    ) -> None:
        """Mirror a verified contract postcondition for the next chat turn.

        The runtime contract remains the authority.  This row is a locked,
        compatibility delivery projection so the next run cannot observe the
        pre-confirmation guided state while the action-result lookup catches
        up across the API and worker session boundary.
        """
        row = await self.get_by_id_for_user(conversation_id, user_id, for_update=True)
        if row is None:
            return
        context = dict(row.context_json or {})
        result = dict(action_result or {})
        target = dict(active_target or {})
        context.pop("active_guided_operation", None)
        context.pop("operation_state", None)
        context["verified_action_result"] = result
        context["verified_action_result_revision"] = int(contract_revision)
        context["active_conversation_target"] = target
        from backend.services.finn_v2_task_chain_service import STATE_KEY, advance_from_action

        task = dict(context.get(STATE_KEY) or {})
        pending_proposal = dict(task.get("pending_action") or {}).get("proposal_id")
        matches_open_action = (
            pending_proposal == result.get("proposal_id") if pending_proposal
            else task.get("expected_run_id") == result.get("run_id")
        )
        if (matches_open_action
                and result.get("owner_user_id") == user_id):
            context[STATE_KEY] = advance_from_action(task, result)
        row.context_json = context
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="record_verified_action_result",
            entity_type="FinnV2Conversation",
            run_id=str(result.get("run_id") or row.last_run_id or ""),
        )
