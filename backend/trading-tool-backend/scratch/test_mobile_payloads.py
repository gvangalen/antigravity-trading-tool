import sys
import os

# Add project root to python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.services.report_service import ReportService
from backend.services.strategy_service import StrategyService

def test_report_mobile_formatting():
    print("📋 Testing ReportService format_report_for_mobile...")
    
    # Mock daily report row
    mock_daily_report = {
        "report_date": "2026-05-11",
        "generated_at": "2026-05-11T21:00:00Z",
        "executive_summary": "Daily performance update.",
        "market_analysis": "Market is consolidating.",
        "outlook": "Bullish transition.",
        "macro_score": 75.0,
        "technical_score": 60.0,
        "market_score": 68.0,
        "setup_score": 85.0,
        "price": 63400.0,
        "change_24h": 2.5,
        "volume": 28000000000.0,
        "market_indicator_highlights": '[{"indicator": "Fear & Greed", "value": "65", "score": 65, "explanation": "Greed territory"}]',
        "macro_indicator_highlights": '[{"indicator": "DXY", "value": "104.2", "score": -5, "explanation": "Weakening DXY is positive"}]',
        "technical_indicator_highlights": '[{"indicator": "RSI BTC 1D", "value": "58", "score": 10, "explanation": "Strong RSI momentum"}]',
        "best_setup": '{"id": 42, "symbol": "BTC", "score": 88}',
        "top_setups": '[{"id": 42, "symbol": "BTC", "score": 88}]',
        "bot_snapshot": '{"active_bots": 3, "pnl": 120.5}',
        "active_strategy": '{"id": 12, "name": "BTC DCA Daily"}',
        "watchlist": '[{"symbol": "BTC", "price": 63400}]'
    }

    # Format
    # Instantiate service without DB session since we are calling the sync formatter method directly
    service = ReportService(repository=None)
    formatted = service.format_report_for_mobile(mock_daily_report)

    # Assertions
    assert formatted["report_date"] == "2026-05-11"
    assert formatted["executive_summary_compact"] == "Daily performance update."
    assert formatted["market_analysis_compact"] == "Market is consolidating."
    assert formatted["outlook_compact"] == "Bullish transition."
    
    # KPIs assertion
    assert formatted["kpi_metrics"]["macro_score"] == 75.0
    assert formatted["kpi_metrics"]["price"] == 63400.0
    assert formatted["kpi_metrics"]["change_24h"] == 2.5

    # Highlights assertion
    assert len(formatted["highlights"]) == 3
    assert formatted["highlights"][0]["category"] == "market"
    assert formatted["highlights"][0]["name"] == "Fear & Greed"
    assert formatted["highlights"][1]["category"] == "macro"
    assert formatted["highlights"][2]["category"] == "technical"

    # Parsed structure assertions
    assert formatted["best_setup"]["id"] == 42
    assert formatted["bot_snapshot"]["active_bots"] == 3
    assert formatted["active_strategy"]["id"] == 12
    assert len(formatted["watchlist"]) == 1

    print("✅ ReportService format_report_for_mobile passed verification!")


def test_strategy_mobile_formatting():
    print("\n📋 Testing StrategyService format_strategy_for_mobile...")
    
    # Mock strategy dict
    mock_strategy = {
        "id": 101,
        "setup_id": 42,
        "setup_name": "BTC Daily DCA",
        "name": "Finn-DCA Strategy",
        "setup_type": "dca",
        "execution_mode": "custom",
        "base_amount": 100.0,
        "symbol": "BTC",
        "timeframe": "1d",
        "entry": None,
        "targets": [],
        "stop_loss": None,
        "risk_reward": "N/A",
        "explanation": "Custom DCA indicator curve strategy.",
        "ai_explanation": "Recommended DCA setup.",
        "risk_profile": "medium",
        "tags": ["DCA", "BTC"],
        "favorite": True,
        "created_at": "2026-05-11T21:00:00Z",
        "decision_curve": [[1, 2], [3, 4], [5, 6]],  # huge coordinate array
        "decision_curve_name": "TrendFollower v2"
    }

    # Instantiate service without DB session
    service = StrategyService(db_session=None)
    formatted = service.format_strategy_for_mobile(mock_strategy)

    # Assertions
    assert formatted["id"] == 101
    assert formatted["name"] == "Finn-DCA Strategy"
    assert formatted["has_decision_curve"] is True
    assert formatted["decision_curve_name"] == "TrendFollower v2"
    assert "decision_curve" not in formatted  # Crucial!

    print("✅ StrategyService format_strategy_for_mobile passed verification!")


if __name__ == "__main__":
    print("🚀 Starting Mobile Payloads Optimization verification suite...")
    try:
        test_report_mobile_formatting()
        test_strategy_mobile_formatting()
        print("\n🎉 All Verification Tests Completed with 100% SUCCESS!")
    except Exception as e:
        print(f"\n❌ Verification failed with error: {e}")
        sys.exit(1)
