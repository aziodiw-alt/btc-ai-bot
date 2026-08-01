import unittest

from alpha_strategy import _avoid_round_number, calculate_alpha_levels


class AlphaLevelTests(unittest.TestCase):
    def test_entries_are_below_current_price_and_staggered(self):
        result = calculate_alpha_levels(
            price=65000,
            support=62500,
            resistance=67000,
            atr=800,
            symbol="BTCUSDT",
        )

        self.assertLess(result["buy_zone_1"][1], 65000)
        self.assertLess(result["buy_zone_2"][1], result["buy_zone_1"][0])
        self.assertEqual(
            [item["allocation_pct"] for item in result["entry_plan"]],
            [20, 30, 50],
        )
        self.assertEqual(
            sum(item["allocation_pct"] for item in result["entry_plan"]),
            100,
        )

    def test_round_number_is_avoided(self):
        self.assertEqual(_avoid_round_number(65005, "BTCUSDT"), 64983.0)
        self.assertNotEqual(_avoid_round_number(65000, "BTCUSDT") % 100, 0)

    def test_trailing_stop_only_activates_after_profit(self):
        result = calculate_alpha_levels(
            price=65000,
            support=62500,
            resistance=67000,
            atr=800,
            symbol="BTCUSDT",
        )

        trailing = result["trailing_stop"]
        self.assertTrue(trailing["enabled_after_profit"])
        self.assertEqual(trailing["activation_price"], result["take_profit_1"])
        self.assertGreater(trailing["protected_stop"], result["planned_entry"])


if __name__ == "__main__":
    unittest.main()
