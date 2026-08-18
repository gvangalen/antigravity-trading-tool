from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class FinnV2RepositoryTransactionMixin:
    session: AsyncSession

    async def _flush_with_rollback(
        self,
        *,
        operation: str,
        entity_type: str,
        run_id: Optional[str] = None,
    ) -> None:
        try:
            await self.session.flush()
        except Exception as exc:
            logger.exception(
                "FINN V2 repository flush failed",
                extra={
                    "repository": self.__class__.__name__,
                    "operation": operation,
                    "entity_type": entity_type,
                    "run_id": run_id,
                    "exception_class": exc.__class__.__name__,
                },
            )
            await self._rollback_after_failure(
                operation=operation,
                entity_type=entity_type,
                run_id=run_id,
            )
            raise

    async def _commit_with_rollback(
        self,
        *,
        operation: str,
        entity_type: str,
        run_id: Optional[str] = None,
    ) -> None:
        try:
            await self.session.commit()
        except Exception as exc:
            logger.exception(
                "FINN V2 repository commit failed",
                extra={
                    "repository": self.__class__.__name__,
                    "operation": operation,
                    "entity_type": entity_type,
                    "run_id": run_id,
                    "exception_class": exc.__class__.__name__,
                },
            )
            await self._rollback_after_failure(
                operation=operation,
                entity_type=entity_type,
                run_id=run_id,
            )
            raise

    async def _rollback_after_failure(
        self,
        *,
        operation: str,
        entity_type: str,
        run_id: Optional[str] = None,
    ) -> None:
        try:
            await self.session.rollback()
        except Exception:
            logger.exception(
                "FINN V2 repository rollback failed",
                extra={
                    "repository": self.__class__.__name__,
                    "operation": operation,
                    "entity_type": entity_type,
                    "run_id": run_id,
                },
            )
