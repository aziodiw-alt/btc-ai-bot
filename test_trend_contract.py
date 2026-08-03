import unittest

from btc_terminal.strategy.trend import score_fast_trend, score_swing_trend


def indicators(ema20, ema50, ema200):
    return {"ema20": ema20, "ema50": ema50, "ema200": ema200}


class TrendScoringContractTest(unittest.TestCase):
    def test_swing_bullish_score_and_reason_order(self):
        self.assertEqual(
            score_swing_trend(
                110,
                indicators(105, 100, 90),
                indicators(108, 103, 95),
            ),
            (
                40,
                [
                    "1D: цена выше EMA200",
                    "1D: EMA20 выше EMA50",
                    "4H: цена выше EMA200",
                    "4H: EMA20 выше EMA50",
                ],
                [],
            ),
        )

    def test_swing_bearish_warning_order(self):
        self.assertEqual(
            score_swing_trend(
                90,
                indicators(95, 100, 105),
                indicators(94, 98, 102),
            ),
            (
                0,
                [],
                [
                    "1D: цена ниже EMA200",
                    "1D: EMA20 ниже EMA50",
                    "4H: цена ниже EMA200",
                    "4H: EMA20 ниже EMA50",
                ],
            ),
        )

    def test_fast_profile_uses_current_weights_and_labels(self):
        self.assertEqual(
            score_fast_trend(
                110,
                indicators(105, 100, 90),
                indicators(108, 103, 95),
            ),
            (
                35,
                [
                    "Fast 4H: цена выше EMA200",
                    "Fast 4H: EMA20 выше EMA50",
                    "Fast 1H: цена выше EMA200",
                    "Fast 1H: EMA20 выше EMA50",
                ],
                [],
            ),
        )


if __name__ == "__main__":
    unittest.main()
