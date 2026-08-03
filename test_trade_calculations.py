import unittest

from btc_terminal.application.trades import (
    classify_order_strategy,
    summarize_open_orders,
)


class OrderStrategyClassificationContractTest(unittest.TestCase):
    def test_buy_inside_fast_zone_keeps_current_confidence(self):
        result = classify_order_strategy(
            100,
            "buy",
            {
                "swing": {"buy_zone_1": (90, 95)},
                "fast": {"buy_zone_1": (99, 101)},
            },
        )

        self.assertEqual(result["strategy_key"], "fast")
        self.assertEqual(result["strategy_confidence"], 95)
        self.assertEqual(
            result["strategy_reason"], "Цена внутри Fast Buy Zone 1"
        )

    def test_distant_sell_target_remains_unclassified(self):
        result = classify_order_strategy(
            100,
            "SELL",
            {"swing": {"take_profit_1": 102}},
        )

        self.assertIsNone(result["strategy_key"])
        self.assertEqual(result["strategy_confidence"], 0)
        self.assertEqual(
            result["strategy_reason"],
            "Ближайший уровень дальше чем на 2.00%",
        )

    def test_open_order_summary_preserves_profit_coverage_contract(self):
        orders, summary = summarize_open_orders([
            {
                "status": "OPEN", "side": "BUY", "order_value": 50,
                "order_quantity": 0.005, "matched_quantity": 0,
                "estimated_profit_usdt": None,
                "estimated_cost_usdt": None,
            },
            {
                "status": "OPEN", "side": "SELL", "order_value": 110,
                "order_quantity": 0.01, "matched_quantity": 0.005,
                "estimated_profit_usdt": 5,
                "estimated_cost_usdt": 50,
            },
            {
                "status": "FILLED", "side": "SELL", "order_value": 200,
                "order_quantity": 0.02, "matched_quantity": 0.02,
                "estimated_profit_usdt": 20,
                "estimated_cost_usdt": 180,
            },
        ])

        self.assertEqual(len(orders), 2)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["buy_count"], 1)
        self.assertEqual(summary["sell_count"], 1)
        self.assertAlmostEqual(summary["expected_profit_pct"], 10)
        self.assertAlmostEqual(summary["profit_coverage_pct"], 50)
        self.assertFalse(summary["profit_is_complete"])


if __name__ == "__main__":
    unittest.main()
