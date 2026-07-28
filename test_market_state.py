import unittest

from market_state import detect_market_state


def indicators(ema20, ema50, ema200):
    return {"ema20": ema20, "ema50": ema50, "ema200": ema200}


class MarketStateTest(unittest.TestCase):
    def test_uptrend_requires_both_timeframes(self):
        result = detect_market_state(
            110,
            indicators(105, 100, 90),
            indicators(108, 103, 95),
        )
        self.assertEqual(result["key"], "UPTREND")

    def test_downtrend_requires_both_timeframes(self):
        result = detect_market_state(
            90,
            indicators(95, 100, 105),
            indicators(94, 98, 102),
        )
        self.assertEqual(result["key"], "DOWNTREND")

    def test_mixed_timeframes_are_range(self):
        result = detect_market_state(
            100,
            indicators(95, 105, 110),
            indicators(105, 98, 95),
        )
        self.assertEqual(result["key"], "RANGE")


if __name__ == "__main__":
    unittest.main()
