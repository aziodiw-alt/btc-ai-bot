import unittest

from web.dashboard_trades import (
    calculate_okx_fifo_statistics,
    calculate_sell_advice,
)


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
        self.assertAlmostEqual(
            advice["free_value_usdt"],
            0.006 * 64500,
        )

    def test_no_advice_without_open_fifo_position(self):
        advice = calculate_sell_advice(
            {"open_quantity": 0, "open_cost": 0}
        )
        self.assertFalse(advice["available"])

    def test_okx_fifo_uses_only_selected_instrument_and_fees(self):
        stats = calculate_okx_fifo_statistics(
            [
                {
                    "instrument": "BTC-USDC",
                    "side": "BUY",
                    "size": 0.01,
                    "value": 640,
                    "fee": -0.00001,
                    "fee_currency": "BTC",
                    "created_at": "2026-07-01T10:00:00+00:00",
                },
                {
                    "instrument": "ETH-USDC",
                    "side": "BUY",
                    "size": 1,
                    "value": 3000,
                    "fee": -0.003,
                    "fee_currency": "ETH",
                    "created_at": "2026-07-01T11:00:00+00:00",
                },
                {
                    "instrument": "BTC-USDC",
                    "side": "SELL",
                    "size": 0.004,
                    "value": 260,
                    "fee": -0.26,
                    "fee_currency": "USDC",
                    "created_at": "2026-07-02T10:00:00+00:00",
                },
            ],
            "BTC-USDC",
        )

        self.assertEqual(stats["execution_count"], 2)
        self.assertAlmostEqual(stats["open_quantity"], 0.00599)
        self.assertGreater(stats["open_cost"], 0)


if __name__ == "__main__":
    unittest.main()
