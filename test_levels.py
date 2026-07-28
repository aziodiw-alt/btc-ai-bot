import unittest

import pandas as pd

from levels import calculate_support_resistance, calculate_trade_levels


class LevelsTest(unittest.TestCase):
    def test_support_and_resistance_use_requested_window(self):
        frame = pd.DataFrame(
            {
                "low": [90, 95, 96],
                "high": [110, 105, 108],
            }
        )

        self.assertEqual(
            calculate_support_resistance(frame, lookback=2),
            (95.0, 108.0),
        )

    def test_swing_buy_zones_are_below_snapshot_price(self):
        result = calculate_trade_levels(
            63_338,
            60_000,
            67_000,
            profile="swing",
        )

        self.assertLess(result["buy_zone_1"][1], 63_338)
        self.assertLess(result["buy_zone_2"][1], result["buy_zone_1"][0])
        self.assertEqual(result["planned_entry"], result["buy_zone_1"][1])

    def test_fast_profile_preserves_existing_percentages(self):
        result = calculate_trade_levels(
            10_000,
            9_500,
            10_500,
            profile="fast",
        )

        self.assertEqual(result["buy_zone_1"], [9_940.0, 9_970.0])
        self.assertEqual(result["buy_zone_2"], [9_880.0, 9_920.0])


if __name__ == "__main__":
    unittest.main()
