"""Recover dated indicator history without inventing scores or source times."""

import asyncio
import logging
import time
from collections import defaultdict

from celery import shared_task
from sqlalchemy import select
from requests import HTTPError

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import UserIndicatorConfig
from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG
from backend.services.indicator_history_bootstrap import (
    ABSOLUTE_MACRO_INDICATORS,
    ABSOLUTE_MARKET_INDICATORS,
    IndicatorHistoryBootstrap,
    RSI_SOURCE_DAYS,
)

logger = logging.getLogger(__name__)
MAX_HISTORY_SCOPES_PER_SWEEP = 4


def _source_failure_code(exc: Exception) -> str:
    """Expose an upstream status without logging request URLs or credentials."""
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"source_http_{exc.response.status_code}"
    return type(exc).__name__


async def _bootstrap_indicator_histories(
    *, user_id: int | None = None, symbol: str | None = None,
    category: str | None = None, indicator: str | None = None,
    enqueue_score_refresh: bool = True,
) -> dict:
    async with async_session_factory() as session:
        query = select(UserIndicatorConfig).where(
            UserIndicatorConfig.enabled.is_(True),
            UserIndicatorConfig.symbol.is_not(None),
            UserIndicatorConfig.category.in_(("market", "macro", "technical")),
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
        market_owners: dict[str, set[int]] = defaultdict(set)
        rsi_owners: dict[str, set[int]] = defaultdict(set)
        macro: dict[tuple[int, str], str] = {}
        for row in rows:
            name = str(row.indicator or "").lower()
            asset = str(row.symbol or "").upper()
            if row.category == "market" and name in ABSOLUTE_MARKET_INDICATORS:
                market[asset].add(name)
                market_owners[asset].add(int(row.user_id))
            elif row.category == "macro" and name in ABSOLUTE_MACRO_INDICATORS:
                macro[(int(row.user_id), name)] = asset
            elif (row.category == "technical" and name == "rsi" and
                  str(getattr(row, "asset_class", None) or
                      DEFAULT_ASSET_CATALOG.get(asset, {}).get("asset_class") or "").lower() == "crypto"):
                market[asset].add("price")
                market_owners[asset].add(int(row.user_id))
                rsi_owners[asset].add(int(row.user_id))
        scopes = [("market", asset, names) for asset, names in sorted(market.items())]
        scopes += [("macro", key, asset) for key, asset in sorted(macro.items())]
        if user_id is None and len(scopes) > MAX_HISTORY_SCOPES_PER_SWEEP:
            start = (int(time.time() // 3600) * MAX_HISTORY_SCOPES_PER_SWEEP) % len(scopes)
            scopes = [scopes[(start + offset) % len(scopes)]
                      for offset in range(MAX_HISTORY_SCOPES_PER_SWEEP)]

        service = IndicatorHistoryBootstrap(session)
        results = []
        score_refreshes: set[int] = set()
        for scope_type, target, extra in scopes:
            try:
                if scope_type == "market":
                    if target in rsi_owners:
                        outcome = await service.bootstrap_market(
                            target, extra, required_price_days=RSI_SOURCE_DAYS,
                        )
                    else:
                        outcome = await service.bootstrap_market(target, extra)
                else:
                    owner_id, name = target
                    outcome = await service.bootstrap_macro(owner_id, name, extra)
                if outcome.get("status") == "ready" and (
                    outcome.get("inserted", 0) > 0 or user_id is not None
                ):
                    if scope_type == "market" and target in rsi_owners:
                        from backend.services.technical_data_service import TechnicalDataService
                        technical = TechnicalDataService(session)
                        materialized = 0
                        for owner_id in sorted(rsi_owners[target]):
                            try:
                                await technical._add_technical_indicator(
                                    "rsi", owner_id, symbol=target, persist_preference=False,
                                )
                                await session.commit()
                                materialized += 1
                            except Exception as exc:
                                await session.rollback()
                                logger.warning(
                                    "RSI materialization pending: category=technical code=%s",
                                    _source_failure_code(exc),
                                )
                        outcome["rsi_materialized"] = materialized
                        outcome["rsi_pending"] = len(rsi_owners[target]) - materialized
                    elif scope_type == "macro":
                        from backend.services.macro_data_service import MacroDataService
                        try:
                            await MacroDataService(session).add_macro_indicator(
                                owner_id, name, None, symbol=extra,
                                persist_preference=False, refresh_existing=True,
                            )
                            await session.commit()
                            outcome["measurement_status"] = "ready"
                        except Exception as exc:
                            await session.rollback()
                            outcome["measurement_status"] = "pending_source"
                            logger.warning(
                                "Macro materialization pending: category=macro indicator=%s code=%s",
                                name, _source_failure_code(exc),
                            )
                results.append({"type": scope_type, "target": str(target), **outcome})
                # A new owner can select an asset whose shared market history
                # is already complete. Rebuild their score even when this run
                # did not need to insert another candle.
                if outcome.get("status") == "ready" and (
                    outcome.get("inserted", 0) > 0 or user_id is not None
                ):
                    if scope_type == "market":
                        score_refreshes.update(market_owners[target])
                    else:
                        score_refreshes.add(owner_id)
            except Exception as exc:
                await session.rollback()
                error_code = _source_failure_code(exc)
                indicator_label = ",".join(sorted(extra)) if scope_type == "market" else target[1]
                logger.warning(
                    "Indicator history bootstrap failed: category=%s indicator=%s code=%s",
                    scope_type, indicator_label, error_code,
                )
                results.append({"type": scope_type, "target": str(target),
                                "status": "source_unavailable", "inserted": 0,
                                "error_code": error_code})
        if score_refreshes and enqueue_score_refresh:
            from backend.celery_task.celery_app import celery_app
            for owner_id in sorted(score_refreshes):
                try:
                    celery_app.send_task(
                        "backend.celery_task.store_daily_scores_task.store_daily_scores_task",
                        kwargs={"user_id": owner_id},
                    )
                except Exception:
                    logger.warning("Score refresh after history bootstrap could not be queued for owner %s",
                                   owner_id, exc_info=True)
        statuses = [result["status"] for result in results]
        logger.info(
            "Indicator history bootstrap completed: attempted=%s ready=%s insufficient=%s unavailable=%s",
            len(results), statuses.count("ready"),
            statuses.count("insufficient_history"), statuses.count("source_unavailable"),
        )
        return {"scopes": results}


@shared_task(name="backend.celery_task.indicator_history_task.bootstrap_indicator_histories")
def bootstrap_indicator_histories(
    user_id: int | None = None, symbol: str | None = None,
    category: str | None = None, indicator: str | None = None,
    enqueue_score_refresh: bool = True,
) -> dict:
    return asyncio.run(_bootstrap_indicator_histories(
        user_id=user_id, symbol=symbol, category=category, indicator=indicator,
        enqueue_score_refresh=enqueue_score_refresh,
    ))
