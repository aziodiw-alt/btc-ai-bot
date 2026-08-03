import unittest

from btc_terminal.strategy.momentum import (
    score_fast_momentum,
    score_swing_momentum,
)


def values(rsi, macd=2, signal=1, histogram=1, previous=0.5):
    return {
        "rsi": rsi,
        "macd": macd,
        "macd_signal": signal,
        "macd_histogram": histogram,
        "macd_histogram_previous": previous,
    }


class MomentumScoringContractTest(unittest.TestCase):
    def test_swing_working_zone_and_bullish_macd(self):
        self.assertEqual(
            score_swing_momentum(values(50)),
            (
                5,
                5,
                ["RSI 4H находится в основной рабочей зоне", "MACD 4H бычий"],
                [],
            ),
        )

    def test_swing_oversold_and_improving_macd(self):
        self.assertEqual(
            score_swing_momentum(values(29, macd=0, signal=1, histogram=-1, previous=-2)),
            (
                1,
                2,
                ["MACD 4H ещё слабый, но импульс улучшается"],
                ["RSI 4H показывает перепроданность и высокий риск"],
            ),
        )

    def test_fast_working_zone_and_bullish_macd(self):
        self.assertEqual(
            score_fast_momentum(values(50)),
            (
                10,
                10,
                ["Fast RSI 1H в рабочей зоне", "Fast MACD 1H бычий"],
                [],
            ),
        )

    def test_fast_histogram_fallback_is_stable(self):
        indicators = {"rsi": 70, "macd": 0, "macd_signal": 1}
        self.assertEqual(
            score_fast_momentum(indicators),
            (
                0,
                0,
                [],
                ["Fast RSI 1H вне рабочей зоны", "Fast MACD 1H слабый"],
            ),
        )


if __name__ == "__main__":
    unittest.main()
