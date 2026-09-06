from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Run, FinnV2RunDispatch


class FinnV2DispatchRepository:
    MAX_ATTEMPTS = 3
    # Beat runs every five seconds. Retry the durable broker handoff before
    # the interactive claim watchdog can dead-letter a message that was
    # accepted by the outbox but not by a worker.
    PUBLISH_RETRY_SECONDS = 5

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **values) -> FinnV2RunDispatch:
        row = FinnV2RunDispatch(**values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_for_run(self, run_id: str) -> Optional[FinnV2RunDispatch]:
        return (await self.session.execute(select(FinnV2RunDispatch).where(FinnV2RunDispatch.run_id == run_id))).scalars().first()

    async def claim(self, *, run_id: str, owner: str, lease_seconds: int) -> Optional[FinnV2RunDispatch]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(FinnV2RunDispatch)
            .where(
                FinnV2RunDispatch.run_id == run_id,
                or_(
                    # A durable handoff is reserved before the synchronous
                    # broker publish begins. The worker is its sole consumer.
                    FinnV2RunDispatch.status == "dispatching",
                    (
                        FinnV2RunDispatch.status.in_(["pending", "retryable_failure"])
                        & FinnV2RunDispatch.lease_expires_at.is_(None)
                    ),
                    (
                        FinnV2RunDispatch.status.in_(["claimed", "running"])
                        & FinnV2RunDispatch.lease_expires_at.is_not(None)
                        & (FinnV2RunDispatch.lease_expires_at < now)
                    ),
                ),
                FinnV2RunDispatch.attempt_count < self.MAX_ATTEMPTS,
                FinnV2RunDispatch.run_id.in_(
                    select(FinnV2Run.id).where(
                        FinnV2Run.status.not_in(
                            [
                                "clarification_required",
                                "unavailable",
                                "downgraded",
                                "rejected",
                                "blocked",
                                "completed",
                                "failed",
                                "canceled",
                            ]
                        )
                    )
                ),
            )
            .values(
                status="claimed",
                owner=owner,
                claimed_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=FinnV2RunDispatch.attempt_count + 1,
                updated_at=now,
            )
            .returning(FinnV2RunDispatch)
        )
        return result.scalars().first()

    async def begin_handoff(self, *, dispatch_id: str, owner: str, lease_seconds: int) -> bool:
        """Reserve a broker handoff before publishing its Celery message.

        Recovery must never republish a row while a direct publish is still
        connecting to the broker. A received task atomically moves this state
        to ``claimed`` before any user processing begins.
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(FinnV2RunDispatch)
            .where(
                FinnV2RunDispatch.dispatch_id == dispatch_id,
                FinnV2RunDispatch.status.in_(["pending", "retryable_failure"]),
            )
            .values(
                status="dispatching",
                owner=owner,
                dispatched_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    async def heartbeat(self, *, dispatch_id: str, owner: str, lease_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(FinnV2RunDispatch)
            .where(
                FinnV2RunDispatch.dispatch_id == dispatch_id,
                FinnV2RunDispatch.owner == owner,
                FinnV2RunDispatch.status.in_(["claimed", "running"]),
            )
            .values(status="running", lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
        )
        return bool(result.rowcount)

    async def mark_published(self, dispatch_id: str) -> None:
        """Record broker handoff without reopening it to concurrent recovery."""
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(FinnV2RunDispatch)
            .where(
                FinnV2RunDispatch.dispatch_id == dispatch_id,
                FinnV2RunDispatch.status == "dispatching",
            )
            .values(
                dispatched_at=now,
                updated_at=now,
            )
        )

    async def reserve_recovery(self, *, dispatch_id: str, owner: str, lease_seconds: int) -> bool:
        """Atomically reserve one stale delivery before re-publishing it.

        Recovery runs can overlap across beat processes.  A row must therefore
        leave its recoverable state before a caller asks the broker to deliver
        it again; reading a stale row alone is not a claim.
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(FinnV2RunDispatch)
            .where(
                FinnV2RunDispatch.dispatch_id == dispatch_id,
                or_(
                    (
                        FinnV2RunDispatch.status.in_(["pending", "retryable_failure"])
                        & FinnV2RunDispatch.lease_expires_at.is_(None)
                        & (FinnV2RunDispatch.next_attempt_at <= now)
                    ),
                    (
                        FinnV2RunDispatch.status.in_(["claimed", "running"])
                        & FinnV2RunDispatch.lease_expires_at.is_not(None)
                        & (FinnV2RunDispatch.lease_expires_at < now)
                    ),
                ),
                FinnV2RunDispatch.attempt_count < self.MAX_ATTEMPTS,
            )
            .values(
                status="dispatching",
                owner=owner,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        return bool(result.rowcount)

    async def mark_completed(self, dispatch_id: str) -> None:
        now = datetime.now(timezone.utc)
        await self.session.execute(update(FinnV2RunDispatch).where(FinnV2RunDispatch.dispatch_id == dispatch_id).values(status="completed", completed_at=now, lease_expires_at=None, updated_at=now))

    async def mark_terminal_failure(self, *, dispatch_id: str, error_code: str) -> None:
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(FinnV2RunDispatch)
            .where(FinnV2RunDispatch.dispatch_id == dispatch_id)
            .values(
                status="terminal_failure",
                last_error_code=error_code[:120],
                owner=None,
                lease_expires_at=None,
                completed_at=now,
                updated_at=now,
            )
        )

    async def mark_failure(self, *, dispatch_id: str, error_code: str) -> str:
        row = (await self.session.execute(select(FinnV2RunDispatch).where(FinnV2RunDispatch.dispatch_id == dispatch_id))).scalars().first()
        if row is None:
            return "terminal_failure"
        now = datetime.now(timezone.utc)
        terminal = row.attempt_count >= self.MAX_ATTEMPTS
        status = "terminal_failure" if terminal else "retryable_failure"
        values = {
            "status": status,
            "last_error_code": error_code[:120],
            "owner": None,
            "lease_expires_at": None,
            "updated_at": now,
            "completed_at": now if terminal else None,
            "next_attempt_at": now + timedelta(seconds=min(60, 2 ** max(row.attempt_count, 1))),
        }
        await self.session.execute(update(FinnV2RunDispatch).where(FinnV2RunDispatch.dispatch_id == dispatch_id).values(**values))
        return status

    async def list_recoverable(self, *, limit: int) -> list[FinnV2RunDispatch]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(FinnV2RunDispatch)
            .where(
                or_(
                    (FinnV2RunDispatch.status.in_(["pending", "retryable_failure"]) & (FinnV2RunDispatch.next_attempt_at <= now)),
                    (
                        FinnV2RunDispatch.status.in_(["claimed", "running"])
                        & FinnV2RunDispatch.lease_expires_at.is_not(None)
                        & (FinnV2RunDispatch.lease_expires_at < now)
                    ),
                ),
                FinnV2RunDispatch.attempt_count < self.MAX_ATTEMPTS,
            )
            .order_by(FinnV2RunDispatch.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def expire_stale_unclaimed(self, *, limit: int, max_age_seconds: int) -> list[FinnV2RunDispatch]:
        """Dead-letter unclaimed delivery rows through one idempotent path."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(FinnV2RunDispatch)
            .where(
                FinnV2RunDispatch.status.in_(["pending", "retryable_failure", "dispatching"]),
                # Creation only makes the durable outbox visible. The gateway
                # can still be handing the row to Celery, so the interactive
                # claim deadline begins at the recorded broker handoff. A
                # ``dispatching`` row has an owner and a lease while the
                # broker accepts or schedules its one permitted delivery;
                # recovery must never terminalize that live reservation just
                # because its published timestamp is older than the generic
                # watchdog age.
                FinnV2RunDispatch.dispatched_at.is_not(None),
                FinnV2RunDispatch.dispatched_at < now - timedelta(seconds=max_age_seconds),
                or_(
                    FinnV2RunDispatch.lease_expires_at.is_(None),
                    FinnV2RunDispatch.lease_expires_at < now,
                ),
            )
            .order_by(FinnV2RunDispatch.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.status = "terminal_failure"
            row.last_error_code = "dispatch_claim_timeout"
            row.completed_at = now
            row.next_attempt_at = now
            row.updated_at = now
        return rows
