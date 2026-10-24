import asyncio

from backend.services.report_service import ReportService, _get_structure_label


class _Repo:
    db = None

    async def get_latest_report(self, user_id, table_name, symbol=None):
        return None


def test_daily_latest_report_returns_pending_first_report_state():
    service = ReportService(_Repo())

    result = asyncio.run(service.get_latest_report(315, "daily_reports", symbol="BTC"))

    assert result["_status"] == "pending_first_report"
    assert "first report" in result["headline"].lower()


def test_report_setup_score_is_never_described_as_trade_conviction():
    label = _get_structure_label(94, "setup")

    assert label == "Nabijheidsscore 94/100"
    assert "%" not in label
    assert "Conviction" not in label
    assert _get_structure_label(94, "setup", "en") == "Proximity score 94/100"
    assert _get_structure_label(94, "setup", "de") == "Nähewert 94/100"
