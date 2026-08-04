import os
import tempfile
import unittest
from unittest.mock import patch

from btc_terminal.storage import paper


def alpha_plan():
    return {
        "entry_plan": [
            {"label": "Entry 1", "allocation_pct": 20, "price": 100},
            {"label": "Entry 2", "allocation_pct": 30, "price": 95},
            {"label": "Entry 3", "allocation_pct": 50, "price": 90},
        ],
        "stop_loss": 80,
        "take_profit_1": 110,
        "take_profit_2": 120,
    }


class PaperTradingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(paper, "DATABASE_PATH", os.path.join(self.temp.name, "paper.db"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_start_creates_alpha_allocations(self):
        paper.start_paper_session("BTCUSDT", 1000, alpha_plan())
        data = paper.get_paper_dashboard("BTCUSDT", 105)
        self.assertEqual([order["allocation_pct"] for order in data["orders"]], [20, 30, 50])
        self.assertAlmostEqual(sum(order["value"] + order["fee"] for order in data["orders"]), 1000, places=6)
        self.assertEqual(paper.get_active_paper_symbols(), ["BTCUSDT"])

    def test_entries_tp1_and_tp2_complete_profitable_cycle(self):
        paper.start_paper_session("BTCUSDT", 1000, alpha_plan())
        filled = paper.evaluate_paper_symbol("BTCUSDT", 90)
        self.assertTrue(all(order["status"] == "FILLED" for order in filled["orders"]))
        before = filled["active"]["asset_balance"]
        after_tp1 = paper.evaluate_paper_symbol("BTCUSDT", 110)
        self.assertAlmostEqual(after_tp1["active"]["asset_balance"], before / 2)
        completed = paper.evaluate_paper_symbol("BTCUSDT", 120)
        self.assertIsNone(completed["active"])
        self.assertEqual(completed["stats"]["completed"], 1)
        self.assertEqual(completed["stats"]["wins"], 1)

    def test_emergency_stop_cancels_pending_orders(self):
        session_id = paper.start_paper_session("ETHUSDT", 200, alpha_plan())
        paper.stop_paper_session(session_id, 105)
        data = paper.get_paper_dashboard("ETHUSDT", 105)
        self.assertIsNone(data["active"])
        self.assertEqual(data["history"][0]["status"], "STOPPED")

    def test_rejects_second_active_session(self):
        paper.start_paper_session("BTCUSDT", 100, alpha_plan())
        with self.assertRaises(ValueError):
            paper.start_paper_session("BTCUSDT", 100, alpha_plan())


if __name__ == "__main__":
    unittest.main()
