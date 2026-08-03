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

    def test_repeated_reactions_beat_isolated_extreme_wicks(self):
        frame = pd.DataFrame(
            {
                "low": [100, 98, 95, 98, 90, 98, 95.2, 98, 97, 99, 98],
                "high": [101, 103, 106, 103, 104, 103, 105.8, 103, 112, 103, 104],
                "close": [100] * 11,
            }
        )

        support, resistance = calculate_support_resistance(frame)

        self.assertAlmostEqual(support, 95.1)
        self.assertAlmostEqual(resistance, 105.9)

    def test_sparse_history_falls_back_to_window_extremes(self):
        frame = pd.DataFrame(
            {
                "low": [90, 95, 96, 97],
                "high": [110, 105, 108, 106],
                "close": [100, 101, 102, 103],
            }
        )

        self.assertEqual(calculate_support_resistance(frame), (90.0, 110.0))

    def test_broken_resistance_can_become_support(self):
        frame = pd.DataFrame(
            {
                "low": [99, 98, 97, 99, 100, 99, 98, 101, 103, 106, 109],
                "high": [101, 103, 102, 105, 103, 104, 105.2, 104, 107, 110, 111],
                "close": [100, 101, 101, 103, 102, 103, 104, 104, 106, 109, 110],
            }
        )

        support, _resistance = calculate_support_resistance(frame)

        self.assertAlmostEqual(support, 105.1)

    def test_swing_buy_zones_are_below_snapshot_price(self):
        result = calculate_trade_levels(
            63_338,
            63_040,
            67_000,
            atr=600,
            profile="swing",
        )

        self.assertLess(result["buy_zone_1"][1], 63_338)
        self.assertLess(result["buy_zone_2"][1], result["buy_zone_1"][0])
        self.assertEqual(result["planned_entry"], result["buy_zone_1"][1])
        self.assertLess(result["stop_loss"], result["buy_zone_2"][0])
        self.assertLessEqual(
            result["support_zone"][0],
            result["buy_zone_1"][0],
        )
        self.assertGreaterEqual(
            result["support_zone"][1],
            result["buy_zone_1"][1],
        )

    def test_fast_profile_uses_support_as_anchor(self):
        result = calculate_trade_levels(
            10_000,
            9_500,
            10_500,
            atr=200,
            profile="fast",
        )

        self.assertEqual(result["support_zone"], [9_476.0, 9_524.0])
        self.assertEqual(result["buy_zone_1"], [9_476.0, 9_524.0])
        self.assertLess(result["buy_zone_2"][1], result["buy_zone_1"][0])

    def test_broken_support_falls_back_below_market(self):
        result = calculate_trade_levels(
            10_000,
            10_200,
            10_800,
            atr=200,
            profile="swing",
        )

        self.assertLess(result["buy_zone_1"][1], 10_000)
        self.assertLess(result["stop_loss"], result["buy_zone_2"][0])


if __name__ == "__main__":
    unittest.main()
