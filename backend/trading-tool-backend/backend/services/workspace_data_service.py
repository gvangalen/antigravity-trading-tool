from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.infrastructure.models import AiCategoryInsight, Watchlist
from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.intelligence_service import IntelligenceService
from backend.services.score_service import ScoreService

logger = logging.getLogger(__name__)

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30, "quarter": 90}
STALE_AFTER_SECONDS = {
    "quote": 5 * 60,
    "day": 36 * 60 * 60,
    "week": 9 * 24 * 60 * 60,
    "month": 35 * 24 * 60 * 60,
    "quarter": 100 * 24 * 60 * 60,
}
DEFAULT_WEIGHTS = {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            return None
    return None


def _freshness(as_of: Any, threshold_seconds: int, source: str) -> dict[str, Any]:
    timestamp = _as_utc(as_of)
    age_seconds = None
    if timestamp is not None:
        age_seconds = max(0, int((datetime.now(timezone.utc) - timestamp).total_seconds()))
    return {
        "source": source,
        "as_of": _iso(as_of),
        "stale": age_seconds is None or age_seconds > threshold_seconds,
        "age_seconds": age_seconds,
        "status": "available" if timestamp is not None else "insufficient_data",
    }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_weights(weights: dict[str, Any] | None) -> dict[str, float]:
    values = {}
    for category, fallback in DEFAULT_WEIGHTS.items():
        value = _number((weights or {}).get(category))
        values[category] = value if value is not None and value >= 0 else fallback
    total = sum(values.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {category: value / total for category, value in values.items()}


def _weighted_score(scores: dict[str, Any], weights: dict[str, Any] | None) -> float | None:
    normalized = _normalized_weights(weights)
    available = [
        (score, normalized[category])
        for category, raw_score in scores.items()
        if (score := _number(raw_score)) is not None and normalized.get(category, 0) > 0
    ]
    included_weight = sum(weight for _, weight in available)
    if included_weight <= 0:
        return None
    return round(sum(score * weight for score, weight in available) / included_weight, 1)


def _materialize_quote_snapshot(row: Any) -> dict[str, Any]:
    return {
        "price": _number(getattr(row, "price", None)),
        "change_24h": _number(getattr(row, "change_24h", None)),
        "volume": _number(getattr(row, "volume", None)),
        "timestamp": getattr(row, "timestamp", None),
    }


def _latest_by_name(rows: Iterable[Any], name_attr: str) -> list[Any]:
    latest: dict[str, Any] = {}
    for row in rows:
        name = str(getattr(row, name_attr, "") or "").strip()
        if not name:
            continue
        current = latest.get(name)
        row_ts = getattr(row, "timestamp", None) or datetime.min
        current_ts = (
            getattr(current, "timestamp", None) or datetime.min
            if current is not None
            else datetime.min
        )
        if current is None or row_ts > current_ts:
            latest[name] = row
    return sorted(latest.values(), key=lambda item: str(getattr(item, name_attr, "")).lower())


def _score_summary(rows: list[dict[str, Any]], period: str) -> dict[str, Any]:
    scores = [row["score"] for row in rows if row.get("value") is not None and row.get("score") is not None]
    if not scores:
        return {
            "score": None,
            "period": period,
            "basis": "indicator_average",
            "status": "insufficient_data",
            "reason": "no_scored_indicators",
            "sample_size": 0,
        }
    return {
        "score": round(sum(scores) / len(scores), 1),
        "period": period,
        "basis": "indicator_average",
        "status": "available",
        "reason": None,
        "sample_size": len(scores),
    }


def _indicator_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _enrich_indicator_rows(
    rows: list[dict[str, Any]],
    *,
    period: str,
    threshold: int,
    source: str,
) -> list[dict[str, Any]]:
    scored = [
        row
        for row in rows
        if row.get("value") is not None and row.get("score") is not None
    ]
    contribution_weight = 1 / len(scored) if scored else 0

    enriched = []
    for row in rows:
        available = row.get("value") is not None
        scored_row = available and row.get("score") is not None
        payload = dict(row)
        payload.update({
            "indicator_key": _indicator_key(row.get("name")),
            "period": period,
            "source": source,
            "freshness": _freshness(row.get("timestamp"), threshold, source),
            "data_status": "available" if available else "insufficient_data",
            "score_contribution": {
                "status": "available" if scored_row else "insufficient_data",
                "basis": "equal_indicator_average",
                "weight": round(contribution_weight, 6) if scored_row else None,
                "weighted_points": (
                    round(float(row["score"]) * contribution_weight, 2)
                    if scored_row
                    else None
                ),
            },
        })
        enriched.append(payload)
    return enriched


def _market_row(row: Any) -> dict[str, Any]:
    return {
        "name": row.name,
        "value": _number(row.value),
        "score": _number(row.score),
        "trend": row.trend,
        "interpretation": row.interpretation,
        "action": row.action,
        "timestamp": _iso(row.timestamp),
        "sample_size": 1,
        "period_aggregate": False,
    }


def _macro_row(row: Any) -> dict[str, Any]:
    return {
        "name": row.name,
        "value": _number(row.value),
        "score": _number(row.score),
        "trend": row.trend,
        "interpretation": row.interpretation,
        "action": row.action,
        "timestamp": _iso(row.timestamp),
        "sample_size": 1,
        "period_aggregate": False,
    }


def _technical_row(row: Any) -> dict[str, Any]:
    return {
        "name": row.indicator,
        "value": _number(row.value),
        "score": _number(row.score),
        "action": row.advies,
        "interpretation": row.uitleg,
        "timestamp": _iso(row.timestamp),
        "sample_size": 1,
        "period_aggregate": False,
    }


def _aggregate_by_name(
    rows: Iterable[Any],
    name_attr: str,
    serializer: Any,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        name = str(getattr(row, name_attr, "") or "").strip()
        if name:
            grouped.setdefault(name, []).append(row)

    aggregated = []
    for name in sorted(grouped, key=str.lower):
        samples = grouped[name]
        latest = max(samples, key=lambda item: getattr(item, "timestamp", None) or datetime.min)
        payload = serializer(latest)
        values = [_number(getattr(item, "value", None)) for item in samples]
        scores = [_number(getattr(item, "score", None)) for item in samples]
        available_values = [value for value in values if value is not None]
        available_scores = [score for score in scores if score is not None]
        payload.update({
            "value": round(sum(available_values) / len(available_values), 6) if available_values else None,
            "score": round(sum(available_scores) / len(available_scores), 1) if available_scores else None,
            "sample_size": len(samples),
            "period_aggregate": True,
        })
        aggregated.append(payload)
    return aggregated


class WorkspaceDataService:
    """Read-only projection for an asset workspace. It never refreshes data or invokes AI."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.market = MarketDataRepository(session)
        self.macro = MacroDataRepository(session)
        self.technical = TechnicalDataRepository(session)
        self.scores = ScoreRepository(session)
        self.users = UserRepository(session)
        self.score_service = ScoreService(self.scores, self.users)
        self.intelligence = IntelligenceService(IntelligenceRepository(session))

    async def get_asset_workspace(
        self,
        user_id: int,
        symbol: str,
        market_period: str,
        macro_period: str,
        technical_period: str,
        watchlist_symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        total_started = perf_counter()
        timings_ms: dict[str, float] = {}

        async def measure(name: str, factory):
            started = perf_counter()
            value = await factory()
            timings_ms[name] = round((perf_counter() - started) * 1000, 2)
            return value

        symbol = str(symbol or "BTC").upper()
        periods = {
            "market": str(market_period or "day").lower(),
            "macro": str(macro_period or "day").lower(),
            "technical": str(technical_period or "day").lower(),
        }
        periods = {key: value if value in PERIOD_DAYS else "day" for key, value in periods.items()}

        # Repositories share this request's AsyncSession. SQLAlchemy sessions may
        # not provision or execute multiple connections concurrently.
        market_rows = await measure("market_rows", lambda: self._market_rows(user_id, symbol, periods["market"]))
        macro_rows = await measure("macro_rows", lambda: self._macro_rows(user_id, symbol, periods["macro"]))
        technical_rows = await measure("technical_rows", lambda: self._technical_rows(user_id, symbol, periods["technical"]))
        quote_snapshot = await measure("quote_snapshot", lambda: self._resolve_quote_snapshot(symbol))
        regime = await measure(
            "regime",
            lambda: self.intelligence.get_market_intelligence(user_id, symbol, allow_compute=False),
        )
        master = await measure("master_score", lambda: self.score_service.get_master_score(user_id, symbol))
        daily = await measure("daily_scores", lambda: self._daily_scores(user_id, symbol))
        session = getattr(self, "session", None)
        asset_catalog = await measure(
            "asset_catalog",
            lambda: AssetCatalogService(session).get_assets([symbol]) if session is not None else self._async_empty_dict(),
        )
        asset_meta = asset_catalog.get(symbol, {})

        quote_payload = {
            "price": quote_snapshot.get("price"),
            "change_24h": quote_snapshot.get("change_24h"),
            "volume": quote_snapshot.get("volume"),
            **_freshness(quote_snapshot.get("timestamp"), STALE_AFTER_SECONDS["quote"], "market_data"),
        }
        categories = {
            "market": self._category_payload(market_rows, periods["market"], STALE_AFTER_SECONDS[periods["market"]], "market_data_indicators"),
            "macro": self._category_payload(macro_rows, periods["macro"], STALE_AFTER_SECONDS[periods["macro"]], "macro_data"),
            "technical": self._category_payload(technical_rows, periods["technical"], STALE_AFTER_SECONDS[periods["technical"]], "technical_indicators"),
        }
        master_payload = master.model_dump() if hasattr(master, "model_dump") else master.dict()
        if not master_payload.get("date"):
            master_payload.update({
                "master_score": None,
                "status": "insufficient_data",
                "reason": "master_score_missing",
            })
        else:
            master_payload.update({"status": "available", "reason": None})
        combined = _weighted_score(
            {category: payload["score"]["score"] for category, payload in categories.items()},
            master_payload.get("weights"),
        )
        effective_watchlist_symbols = (
            watchlist_symbols
            if watchlist_symbols
            else await self._fetch_user_watchlist_symbols(user_id)
        )
        watchlist_payload = await measure(
            "watchlist",
            lambda: self._build_watchlist_payload(
                user_id,
                effective_watchlist_symbols or [symbol],
                master_payload.get("weights"),
            ),
        )
        finn_snapshot = await measure(
            "finn_snapshot",
            lambda: self._build_finn_snapshot(user_id, symbol, master_payload, regime, daily),
        )
        timings_ms["total"] = round((perf_counter() - total_started) * 1000, 2)
        if timings_ms["total"] > 500:
            logger.info(
                "Workspace snapshot latency user_id=%s symbol=%s timings_ms=%s",
                user_id,
                symbol,
                timings_ms,
            )

        return {
            "symbol": symbol,
            "asset": {
                "symbol": symbol,
                "display_name": asset_meta.get("display_name") or symbol,
                "asset_class": asset_meta.get("asset_class") or "unknown",
                "logo_url": asset_meta.get("logo_url"),
                "tradingview_symbol": asset_meta.get("tradingview_symbol"),
            },
            "periods": periods,
            "quote": quote_payload,
            "categories": categories,
            "combined": {
                "score": combined,
                "periods": periods,
                "basis": "weighted_category_average",
                "weights": _normalized_weights(master_payload.get("weights")),
                "status": "available" if combined is not None else "insufficient_data",
            },
            "daily": daily,
            "master": master_payload,
            "watchlist": watchlist_payload,
            "regime": regime,
            "finn": finn_snapshot,
            "timings_ms": timings_ms,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ai_calls": 0,
        }

    async def _daily_scores(self, user_id: int, symbol: str) -> dict[str, Any] | None:
        try:
            payload = await self.score_service.get_daily_scores(user_id, symbol)
        except LookupError:
            return None
        return payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()

    async def get_watchlist(self, user_id: int, symbols: list[str]) -> dict[str, Any]:
        user = await self.users.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", None) or {}
        weights = preferences.get("intelligence_weights", {})
        return await self._build_watchlist_payload(user_id, symbols, weights)

    async def _build_watchlist_payload(
        self,
        user_id: int,
        symbols: list[str],
        weights: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = list(dict.fromkeys(str(symbol).upper() for symbol in symbols if symbol))[:25]
        if not normalized:
            return {
                "period": "day",
                "weights": _normalized_weights(weights),
                "rows": [],
                "ai_calls": 0,
            }

        quote_map = await self._resolve_quote_map(normalized)
        scores = await self.scores.fetch_daily_scores_batch(user_id, normalized)
        session = getattr(self, "session", None)
        asset_catalog = await AssetCatalogService(session).get_assets(normalized) if session is not None else {}
        rows = []
        for symbol in normalized:
            quote = quote_map.get(symbol)
            daily = scores.get(symbol)
            asset_meta = asset_catalog.get(symbol, {})
            category_scores = [
                _number(daily.get(key)) if daily else None
                for key in ("market_score", "macro_score", "technical_score")
            ]
            combined = _weighted_score(
                dict(zip(("market", "macro", "technical"), category_scores)),
                weights,
            )
            score_freshness = _freshness(
                daily.get("report_date") if daily else None,
                STALE_AFTER_SECONDS["day"],
                "daily_scores",
            )
            rows.append({
                "symbol": symbol,
                "display_name": asset_meta.get("display_name") or symbol,
                "asset_class": asset_meta.get("asset_class") or "unknown",
                "logo_url": asset_meta.get("logo_url"),
                "tradingview_symbol": asset_meta.get("tradingview_symbol"),
                "price": quote.get("price") if quote else None,
                "change_24h": quote.get("change_24h") if quote else None,
                "score": combined,
                "score_period": "day",
                "score_status": "available" if combined is not None else "insufficient_data",
                "quote": _freshness(quote.get("timestamp") if quote else None, STALE_AFTER_SECONDS["quote"], "market_data"),
                "score_freshness": score_freshness,
            })
        return {
            "period": "day",
            "weights": _normalized_weights(weights),
            "rows": rows,
            "ai_calls": 0,
        }

    async def _fetch_user_watchlist_symbols(self, user_id: int) -> list[str]:
        stmt = select(Watchlist.symbol).where(Watchlist.user_id == user_id).order_by(Watchlist.created_at.asc(), Watchlist.id.asc())
        result = await self.session.execute(stmt)
        return [str(symbol or "").upper() for symbol in result.scalars().all() if symbol]

    async def _resolve_quote_snapshot(self, symbol: str) -> dict[str, Any]:
        quote_map = await self._resolve_quote_map([symbol])
        return quote_map.get(str(symbol or "").upper(), {})

    async def _resolve_quote_map(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys(str(symbol).upper() for symbol in symbols if symbol))
        if not normalized:
            return {}

        if hasattr(self.market, "get_latest_snapshots"):
            quotes = await self.market.get_latest_snapshots(normalized)
        else:
            quotes = []
            for symbol in normalized:
                snapshot = await self.market.get_latest_snapshot(symbol)
                if snapshot is not None:
                    quotes.append(snapshot)
        quote_map: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(quotes):
            symbol = str(getattr(row, "symbol", "")).upper()
            if not symbol and len(normalized) == 1:
                symbol = normalized[0]
            elif not symbol and index < len(normalized):
                symbol = normalized[index]
            if not symbol:
                continue
            quote_map[symbol] = _materialize_quote_snapshot(row)
        return quote_map

    async def _build_finn_snapshot(
        self,
        user_id: int,
        symbol: str,
        master_payload: dict[str, Any],
        regime: dict[str, Any] | None,
        daily: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not hasattr(self.session, "execute"):
            return {
                "status": "unavailable",
                "source": "workspace_snapshot",
                "symbol": symbol,
                "headline": None,
                "summary": None,
                "risk_summary": None,
                "master_bias": master_payload.get("master_bias") or "–",
                "master_risk": master_payload.get("master_risk") or "–",
                "regime": "unknown",
                "strongest_category": None,
                "categories": {},
                "freshness": _freshness(master_payload.get("date"), STALE_AFTER_SECONDS["day"], "workspace_snapshot"),
                "as_of": _iso(master_payload.get("date")),
            }
        categories = ("market", "macro", "technical")
        insights: dict[str, dict[str, Any]] = {}
        latest_dates: list[Any] = []

        for category in categories:
            stmt = (
                select(AiCategoryInsight)
                .where(
                    AiCategoryInsight.user_id == user_id,
                    AiCategoryInsight.category == category,
                    AiCategoryInsight.symbol == symbol,
                )
                .order_by(AiCategoryInsight.date.desc(), AiCategoryInsight.id.desc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            row = result.scalars().first()
            if not row:
                continue
            insights[category] = {
                "summary": row.summary or "",
                "bias": row.bias or "–",
                "risk": row.risk or "–",
                "score": _number(row.avg_score),
                "as_of": _iso(row.date),
            }
            latest_dates.append(row.date)

        master_summary = str(master_payload.get("summary") or "").strip()
        master_date = master_payload.get("date")
        freshness = _freshness(master_date, STALE_AFTER_SECONDS["day"], "workspace_snapshot")
        regime_label = (
            regime.get("regime_label")
            or regime.get("label")
            or regime.get("phase")
            or regime.get("market_phase")
            or "unknown"
        ) if isinstance(regime, dict) else "unknown"
        strongest_category = max(
            (
                (name, _number((daily or {}).get(name, {}).get("score")))
                for name in categories
            ),
            key=lambda item: item[1] if item[1] is not None else float("-inf"),
            default=(None, None),
        )[0]

        if master_summary:
            headline = master_summary
            summary = master_summary
            status = "available"
        else:
            headline = None
            summary = None
            status = "unavailable"

        return {
            "status": status,
            "source": "workspace_snapshot",
            "symbol": symbol,
            "headline": headline,
            "summary": summary,
            "risk_summary": master_payload.get("outlook") or None,
            "master_bias": master_payload.get("master_bias") or "–",
            "master_risk": master_payload.get("master_risk") or "–",
            "regime": regime_label,
            "strongest_category": strongest_category,
            "categories": insights,
            "freshness": freshness,
            "as_of": _iso(master_date or (max(latest_dates) if latest_dates else None)),
        }

    async def _async_empty_dict(self) -> dict[str, Any]:
        return {}

    async def get_indicator_detail(
        self,
        user_id: int,
        symbol: str,
        category: str,
        period: str,
        indicator: str,
    ) -> dict[str, Any] | None:
        symbol = str(symbol or "BTC").upper()
        category = str(category or "").lower()
        period = str(period or "day").lower()
        if category not in {"market", "macro", "technical"}:
            return None
        if period not in PERIOD_DAYS:
            period = "day"

        if category == "market":
            rows = await self._market_rows(user_id, symbol, period)
            source = "market_data_indicators"
        elif category == "macro":
            rows = await self._macro_rows(user_id, symbol, period)
            source = "macro_data"
        else:
            rows = await self._technical_rows(user_id, symbol, period)
            source = "technical_indicators"

        category_payload = self._category_payload(
            rows,
            period,
            STALE_AFTER_SECONDS[period],
            source,
        )
        target = _indicator_key(indicator)
        row = next(
            (item for item in category_payload["rows"] if item.get("indicator_key") == target),
            None,
        )
        if row is None:
            return None
        return {
            "symbol": symbol,
            "category": category,
            "period": period,
            "indicator": row,
            "category_score": category_payload["score"],
            "category_freshness": category_payload["freshness"],
            "ai_calls": 0,
        }

    async def _market_rows(self, user_id: int, symbol: str, period: str) -> list[dict[str, Any]]:
        allowed: set[str] = set()
        resolver = getattr(self.market, "resolve_effective_preferences", None)
        if callable(resolver):
            resolved = await resolver(user_id, symbol=symbol)
            allowed = {
                _indicator_key(row.indicator)
                for row in resolved.get("rows", [])
                if str(row.indicator or "").strip()
            }
        if period == "day":
            rows = await self.market.get_active_day_indicators(user_id, symbol)
            payload = [_market_row(row) for row in _latest_by_name(rows, "name")]
            return [row for row in payload if not allowed or _indicator_key(row.get("name")) in allowed]
        else:
            rows = await self.market.get_period_indicators(user_id, symbol, PERIOD_DAYS[period])
            payload = _aggregate_by_name(rows, "name", _market_row)
            return [row for row in payload if not allowed or _indicator_key(row.get("name")) in allowed]

    async def _macro_rows(self, user_id: int, symbol: str, period: str) -> list[dict[str, Any]]:
        allowed: set[str] = set()
        resolver = getattr(self.macro, "resolve_effective_preferences", None)
        if callable(resolver):
            resolved = await resolver(user_id, symbol=symbol)
            allowed = {
                _indicator_key(row.indicator)
                for row in resolved.get("rows", [])
                if str(row.indicator or "").strip()
            }
        if period == "day":
            rows = await self.macro.get_active_day_macro_data(user_id, symbol)
            payload = [_macro_row(row) for row in _latest_by_name(rows, "name")]
            return [row for row in payload if not allowed or _indicator_key(row.get("name")) in allowed]
        else:
            rows = await self.macro._get_data_by_days(user_id, PERIOD_DAYS[period], symbol=symbol)
            payload = _aggregate_by_name(rows, "name", _macro_row)
            return [row for row in payload if not allowed or _indicator_key(row.get("name")) in allowed]

    async def _technical_rows(self, user_id: int, symbol: str, period: str) -> list[dict[str, Any]]:
        allowed: set[str] = set()
        resolver = getattr(self.technical, "resolve_effective_preferences", None)
        if callable(resolver):
            resolved = await resolver(user_id, symbol=symbol)
            allowed = {
                _indicator_key(row.indicator)
                for row in resolved.get("rows", [])
                if str(row.indicator or "").strip()
            }
        if period == "day":
            rows = await self.technical.get_day_data(user_id, symbol)
            payload = [_technical_row(row) for row in _latest_by_name(rows, "indicator")]
            return [row for row in payload if not allowed or _indicator_key(row.get("name")) in allowed]
        elif period == "week":
            rows = await self.technical.get_week_data(user_id, symbol)
        elif period == "month":
            rows = await self.technical.get_month_data(user_id, symbol)
        else:
            rows = await self.technical.get_quarter_data(user_id, symbol)
        payload = _aggregate_by_name(rows, "indicator", _technical_row)
        return [row for row in payload if not allowed or _indicator_key(row.get("name")) in allowed]

    @staticmethod
    def _category_payload(
        rows: list[dict[str, Any]],
        period: str,
        threshold: int,
        source: str,
    ) -> dict[str, Any]:
        timestamps = [row.get("timestamp") for row in rows if row.get("timestamp")]
        latest_timestamp = max(timestamps) if timestamps else None
        enriched_rows = _enrich_indicator_rows(
            rows,
            period=period,
            threshold=threshold,
            source=source,
        )
        return {
            "rows": enriched_rows,
            "score": _score_summary(enriched_rows, period),
            "freshness": _freshness(
                datetime.fromisoformat(latest_timestamp) if latest_timestamp else None,
                threshold,
                source,
            ),
        }
