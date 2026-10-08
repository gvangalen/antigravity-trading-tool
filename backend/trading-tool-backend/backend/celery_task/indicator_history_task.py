"""Recover dated indicator history without inventing scores or source times."""

import asyncio
import logging
import time
from collections import defaultdict

from celery import shared_task
from sqlalchemy import select

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import UserIndicatorConfig
from backend.services.indicator_history_bootstrap import (
    ABSOLUTE_MACRO_INDICATORS,
    ABSOLUTE_MARKET_INDICATORS,
    IndicatorHistoryBootstrap,
)

logger = logging.getLogger(__name__)
MAX_HISTORY_SCOPES_PER_SWEEP = 4


async def _bootstrap_indicator_histories(
    *, user_id: int | None = None, symbol: str | None = None,
    category: str | None = None, indicator: str | None = None,
) -> dict:
    async with async_session_factory() as session:
        query = select(UserIndicatorConfig).where(
            UserIndicatorConfig.enabled.is_(True),
            UserIndicatorConfig.symbol.is_not(None),
            UserIndicatorConfig.category.in_(("market", "macro")),
        )
        if user_id is not None:
            query = query.where(UserIndicatorConfig.user_id == int(user_id))
        if symbol is not None:
            query = query.where(UserIndicatorConfig.symbol == str(symbol).upper())
        if category is not None:
            query = query.where(UserIndicatorConfig.category == category)
        if indicator is not None:
            query = query.where(UserIndicatorConfig.indicator == indicator.lower())
        rows = (await session.execute(query)).scalars().all()

        market: dict[str, set[str]] = defaultdict(set)
        macro: dict[tuple[int, str], str] = {}
        for row in rows:
            name = str(row.indicator or "").lower()
            asset = str(row.symbol or "").upper()
            if row.category == "market" and name in ABSOLUTE_MARKET_INDICATORS:
                market[asset].add(name)
            elif row.category == "macro" and name in ABSOLUTE_MACRO_INDICATORS:
                macro[(int(row.user_id), name)] = asset
        scopes = [("market", asset, names) for asset, names in sorted(market.items())]
        scopes += [("macro", key, asset) for key, asset in sorted(macro.items())]
        if user_id is None and len(scopes) > MAX_HISTORY_SCOPES_PER_SWEEP:
            start = (int(time.time() // 3600) * MAX_HISTORY_SCOPES_PER_SWEEP) % len(scopes)
            scopes = [scopes[(start + offset) % len(scopes)]
                      for offset in range(MAX_HISTORY_SCOPES_PER_SWEEP)]

        service = IndicatorHistoryBootstrap(session)
        results = []
        for scope_type, target, extra in scopes:
            try:
                if scope_type == "market":
                    outcome = await service.bootstrap_market(target, extra)
                else:
                    owner_id, name = target
                    outcome = await service.bootstrap_macro(owner_id, name, extra)
                results.append({"type": scope_type, "target": str(target), **outcome})
            except Exception as exc:
                await session.rollback()
                logger.warning("Indicator history bootstrap failed for %s %s: %s",
                               scope_type, target, type(exc).__name__)
                results.append({"type": scope_type, "target": str(target),
                                "status": "source_unavailable", "inserted": 0})
        return {"scopes": results}


@shared_task(name="backend.celery_task.indicator_history_task.bootstrap_indicator_histories")
def bootstrap_indicator_histories(
    user_id: int | None = None, symbol: str | None = None,
    category: str | None = None, indicator: str | None = None,
) -> dict:
    return asyncio.run(_bootstrap_indicator_histories(
        user_id=user_id, symbol=symbol, category=category, indicator=indicator,
    ))
