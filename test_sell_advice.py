import unittest

from web.dashboard_trades import calculate_sell_advice


class SellAdviceTests(unittest.TestCase):
    def test_targets_are_net_of_future_sell_fee(self):
        advice = calculate_sell_advice(
            {
                "open_quantity": 0.01,
                "open_cost": 640,
            },
            current_price=64500,
            pending_sell_quantity=0.004,
        )

        self.assertTrue(advice["available"])
        self.assertAlmostEqual(advice["average_buy_price"], 64000)
        self.assertAlmostEqual(
            advice["target_price_15"],
            64000 * 1.015 / 0.999,
        )
        self.assertAlmostEqual(
            advice["target_price_20"],
            64000 * 1.020 / 0.999,
        )
        self.assertAlmostEqual(advice["reserved_quantity"], 0.004)
        self.assertAlmostEqual(advice["free_quantity"], 0.006)

    def test_no_advice_without_open_fifo_position(self):
        advice = calculate_sell_advice(
            {"open_quantity": 0, "open_cost": 0}
        )
        self.assertFalse(advice["available"])


if __name__ == "__main__":
    unittest.main()
