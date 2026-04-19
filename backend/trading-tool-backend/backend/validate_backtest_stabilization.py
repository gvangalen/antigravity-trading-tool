import sys
import os
from datetime import date, timedelta
import unittest
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.engine.backtest_engine import run_bot_backtest
from backend.engine.bot_brain import run_bot_brain
from backend.utils.db import get_db_connection

class TestBacktestStabilization(unittest.TestCase):

    def setUp(self):
        self.user_id = 30
        self.bot_id = 16
        self.strategy_id = 63

    @patch('backend.engine.backtest_engine.get_db_connection')
    @patch('backend.engine.backtest_engine.get_historical_candles')
    @patch('backend.engine.backtest_engine.run_bot_brain')
    @patch('backend.engine.backtest_engine._get_daily_scores')
    @patch('backend.engine.backtest_engine._get_active_strategy_snapshot')
    @patch('backend.engine.backtest_engine._get_strategy_setup_payload')
    def test_sell_parity(self, mock_setup, mock_snap, mock_scores, mock_brain, mock_candles, mock_db):
        """Verify that Brain SELL closes an existing position."""
        mock_scores.return_value = {"macro": 80, "technical": 80, "market": 80, "setup": 80}
        mock_snap.return_value = {"setup_type": "trade", "entry": 60000, "stop_loss": 50000, "targets": [70000], "confidence": 90}
        mock_setup.return_value = {"setup_type": "trade"}

        mock_candles.return_value = [
            {"date": date.today() - timedelta(days=1), "open": 60000, "high": 61000, "low": 59000, "close": 60500, "volume": 100},
            {"date": date.today(), "open": 60500, "high": 62000, "low": 60000, "close": 61500, "volume": 100},
        ]

        mock_brain.side_effect = [
            {
                "action": "buy", "amount_eur": 1000, "confidence": 0.8, "reason": "test_buy",
                "trade_plan": {"stop_loss": {"price": 50000}, "targets": [{"price": 70000}]}
            },
            {
                "action": "sell", "amount_eur": 0, "confidence": 0.9, "reason": "brain_exit_signal"
            }
        ]

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = (16, "Bot", 63, 1, "BTC", "1d", 100000, 5000, 10, 1000, 100, "trade")

        res = run_bot_backtest(self.user_id, self.bot_id, days=2)

        self.assertTrue(res["ok"])
        self.assertEqual(res["total_trades"], 2)
        self.assertEqual(res["trades"][1]["side"], "sell")
        self.assertEqual(res["trades"][1]["reason"], "brain_exit_signal")
        print("✅ PASS: SELL Parity")

    @patch('backend.engine.backtest_engine.get_db_connection')
    @patch('backend.engine.backtest_engine.get_historical_candles')
    @patch('backend.engine.backtest_engine.run_bot_brain')
    @patch('backend.engine.backtest_engine._get_daily_scores')
    @patch('backend.engine.backtest_engine._get_active_strategy_snapshot')
    @patch('backend.engine.backtest_engine._get_strategy_setup_payload')
    def test_exit_priority(self, mock_setup, mock_snap, mock_scores, mock_brain, mock_candles, mock_db):
        """Verify TP/SL hit takes priority over Brain SELL in the same candle."""
        mock_scores.return_value = {"macro": 80, "technical": 80, "market": 80, "setup": 80}
        mock_snap.return_value = {"setup_type": "trade", "entry": 60000, "stop_loss": 50000, "targets": [70000], "confidence": 90}
        mock_setup.return_value = {"setup_type": "trade"}

        mock_candles.return_value = [
            {"date": date.today() - timedelta(days=1), "open": 60000, "high": 61000, "low": 59000, "close": 60500, "volume": 100},
            {"date": date.today(), "open": 60500, "high": 75000, "low": 60000, "close": 74000, "volume": 100},
        ]
        
        mock_brain.side_effect = [
            {
                "action": "buy", "amount_eur": 1000, "confidence": 0.8, "reason": "test_buy",
                "trade_plan": {"stop_loss": {"price": 50000}, "targets": [{"price": 70000}]}
            },
            {
                "action": "sell", "amount_eur": 0, "confidence": 0.9, "reason": "brain_exit_signal"
            }
        ]

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = (16, "Bot", 63, 1, "BTC", "1d", 100000, 5000, 10, 1000, 100, "trade")

        res = run_bot_backtest(self.user_id, self.bot_id, days=2)

        self.assertTrue(res["ok"])
        self.assertEqual(res["trades"][1]["reason"], "take_profit")
        self.assertEqual(res["trades"][1]["price"], 70000)
        print("✅ PASS: Exit Priority")

    @patch('backend.engine.backtest_engine.get_db_connection')
    @patch('backend.engine.backtest_engine.get_historical_candles')
    @patch('backend.engine.bot_brain.apply_guardrails')
    @patch('backend.engine.backtest_engine._get_daily_scores')
    @patch('backend.engine.backtest_engine._get_active_strategy_snapshot')
    @patch('backend.engine.backtest_engine._get_strategy_setup_payload')
    def test_guardrails_backtest_mode(self, mock_setup, mock_snap, mock_scores, mock_guard, mock_candles, mock_db):
        """Verify backtest_mode=True reaches guardrails."""
        mock_scores.return_value = {"macro": 80, "technical": 80, "market": 80, "setup": 80}
        mock_snap.return_value = {"setup_type": "trade", "entry": 60000, "stop_loss": 50000, "targets": [70000], "confidence": 90}
        mock_setup.return_value = {"setup_type": "trade"}
        mock_candles.return_value = [{"date": date.today(), "open": 60000, "high": 61000, "low": 59000, "close": 60500, "volume": 100}]
        
        mock_guard.return_value = {"allowed": True, "adjusted_amount_eur": 1000}
        
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = (16, "Bot", 63, 1, "BTC", "1d", 500, 500, 10, 1000, 100, "trade")

        res = run_bot_backtest(self.user_id, self.bot_id, days=1)

        args, kwargs = mock_guard.call_args
        self.assertTrue(kwargs.get("backtest_mode"))
        print("✅ PASS: Guardrails Backtest Mode")

    @patch('backend.engine.backtest_engine.get_db_connection')
    @patch('backend.engine.backtest_engine.get_historical_candles')
    @patch('backend.engine.backtest_engine.run_bot_brain')
    @patch('backend.engine.backtest_engine._get_daily_scores')
    @patch('backend.engine.backtest_engine._get_active_strategy_snapshot')
    @patch('backend.engine.backtest_engine._get_strategy_setup_payload')
    def test_extreme_candle(self, mock_setup, mock_snap, mock_scores, mock_brain, mock_candles, mock_db):
        """Verify exit triggers at EXACT target price even in extreme candle."""
        mock_scores.return_value = {"macro": 80, "technical": 80, "market": 80, "setup": 80}
        mock_snap.return_value = {"setup_type": "trade", "entry": 60000, "stop_loss": 50000, "targets": [70000], "confidence": 90}
        mock_setup.return_value = {"setup_type": "trade"}

        mock_candles.return_value = [
            {"date": date.today() - timedelta(days=1), "open": 60000, "high": 61000, "low": 59000, "close": 60000, "volume": 100},
            {"date": date.today(), "open": 60000, "high": 100000, "low": 60000, "close": 90000, "volume": 100},
        ]

        mock_brain.side_effect = [
            {
                "action": "buy", "amount_eur": 1000, "confidence": 0.8,
                "trade_plan": {"stop_loss": {"price": 50000}, "targets": [{"price": 70000}]}
            },
            {"action": "hold"}
        ]

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = (16, "Bot", 63, 1, "BTC", "1d", 100000, 5000, 10, 1000, 100, "trade")

        res = run_bot_backtest(self.user_id, self.bot_id, days=2)

        self.assertEqual(res["trades"][1]["price"], 70000)
        print("✅ PASS: Extreme Candle")

    @patch('backend.engine.backtest_engine.get_db_connection')
    @patch('backend.engine.backtest_engine.get_historical_candles')
    @patch('backend.engine.backtest_engine._get_daily_scores')
    @patch('backend.engine.backtest_engine._get_active_strategy_snapshot')
    @patch('backend.engine.backtest_engine._get_strategy_setup_payload')
    def test_mini_data(self, mock_setup, mock_snap, mock_scores, mock_candles, mock_db):
        """Verify engine doesn't crash with missing daily data."""
        mock_candles.return_value = [{"date": date.today(), "open": 60000, "high": 61000, "low": 59000, "close": 60500, "volume": 100}]
        mock_scores.return_value = None 
        mock_snap.return_value = None
        mock_setup.return_value = {"setup_type": "trade"}

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        mock_cur.fetchone.return_value = (16, "Bot", 63, 1, "BTC", "1d", 100000, 5000, 10, 1000, 100, "trade")

        res = run_bot_backtest(self.user_id, self.bot_id, days=1)
        self.assertTrue(res["ok"])
        print("✅ PASS: Mini Data Robustness")

if __name__ == "__main__":
    unittest.main()
