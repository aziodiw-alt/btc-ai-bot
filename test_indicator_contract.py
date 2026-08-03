import unittest

import pandas as pd

from indicators import analyze


class IndicatorContractTest(unittest.TestCase):
    def test_indicator_snapshot_on_deterministic_candles(self):
        close = [
            100.0 + index * 0.5 + ((index % 7) - 3) * 0.1
            for index in range(250)
        ]
        frame = pd.DataFrame(
            {
                "close": close,
                "high": [value + 2 for value in close],
                "low": [value - 2 for value in close],
            }
        )

        self.assertEqual(
            analyze(frame),
            {
                "rsi": 97.54,
                "ema20": 219.74,
                "ema50": 212.25,
                "ema200": 178.85,
                "macd": 3.5,
                "macd_signal": 3.5,
                "macd_histogram": 0.0,
                "macd_histogram_previous": -0.01,
                "atr": 4.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
