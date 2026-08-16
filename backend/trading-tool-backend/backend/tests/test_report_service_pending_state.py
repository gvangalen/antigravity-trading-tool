import asyncio

from backend.services.report_service import ReportService


class _Repo:
    db = None

    async def get_latest_report(self, user_id, table_name, symbol=None):
        return None


def test_daily_latest_report_returns_pending_first_report_state():
    service = ReportService(_Repo())

    result = asyncio.run(service.get_latest_report(315, "daily_reports", symbol="BTC"))

    assert result["_status"] == "pending_first_report"
    assert "first report" in result["headline"].lower()
