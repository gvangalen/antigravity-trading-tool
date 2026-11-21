from __future__ import annotations

from datetime import date, datetime, timezone

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.schemas.finn_v2_evidence_schema import (
    ForwardReturnPartialData,
    ForwardReturnsData,
    ForwardReturnYearData,
)


PERIODS = {"week": ("7d", 53), "month": ("30d", 12), "quarter": ("90d", 4), "year": ("365d", 1)}
MAX_YEARS = 10


class ForwardReturnsToolAdapter:
    """Read the same stored returns used by the asset workspace, without starting a sync."""

    def __init__(self, session):
        self.repository = MarketDataRepository(session)

    async def execute(self, *, asset: str, **_kwargs):
        symbol = asset.upper()
        records = await self.repository.get_forward_returns(symbol)
        if not records:
            raise LookupError("source_unavailable")

        today = datetime.now(timezone.utc).date()
        first_year = today.year - MAX_YEARS + 1
        periods = {}
        partial = {}
        for name, (stored_period, width) in PERIODS.items():
            by_year = {}
            for record in records:
                if record.period != stored_period or record.change is None:
                    continue
                start = self._as_date(record.start_date)
                end = self._as_date(record.end_date)
                if start is None or end is None:
                    continue
                year, index = self._calendar_position(name, start)
                if year < first_year or year > today.year:
                    continue
                values = by_year.setdefault(year, [None] * width)
                values[index] = float(record.change)
                if self._is_current_period(name, start, today):
                    partial[name] = ForwardReturnPartialData(
                        year=year,
                        index=index,
                        value=float(record.change),
                        observed_through=end,
                    )
            periods[name] = [ForwardReturnYearData(year=year, values=values) for year, values in sorted(by_year.items())]

        if not any(periods.values()):
            raise LookupError("source_unavailable")
        latest_created = max((record.created_at for record in records if record.created_at), default=None)
        history_start = min((value for record in records if (value := self._as_date(record.start_date))), default=None)
        latest_observed = max((value for record in records if (value := self._as_date(record.end_date))), default=None)
        data = ForwardReturnsData(
            symbol=symbol,
            as_of=latest_created,
            history_start=history_start,
            observed_through=latest_observed,
            periods=periods,
            partial=partial,
        )
        return {
            "data": data,
            "summary": {"title": "forward_returns", "symbol": symbol, "periods": list(PERIODS), "years": MAX_YEARS},
            "as_of": latest_created,
            "source": "market_forward_returns",
            "schema_name": "ForwardReturnsData",
            "entity_type": "forward_returns",
            "asset": symbol,
        }

    @staticmethod
    def _as_date(value: date | datetime | None) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return None

    @staticmethod
    def _calendar_position(period: str, start: date) -> tuple[int, int]:
        if period == "week":
            # Match the year/ISO-week placement used by the visible table.
            return start.year, start.isocalendar().week - 1
        if period == "month":
            return start.year, start.month - 1
        if period == "quarter":
            return start.year, (start.month - 1) // 3
        return start.year, 0

    @staticmethod
    def _is_current_period(period: str, start: date, today: date) -> bool:
        if period == "week":
            return start.isocalendar()[:2] == today.isocalendar()[:2]
        if period == "month":
            return (start.year, start.month) == (today.year, today.month)
        if period == "quarter":
            return (start.year, (start.month - 1) // 3) == (today.year, (today.month - 1) // 3)
        return start.year == today.year
