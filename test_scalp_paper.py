import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from btc_terminal.storage import scalp_paper


def signal_candles():
    prices = [100 + index * 0.03 for index in range(35)]
    # A small pullback keeps RSI inside the entry range, followed by momentum.
    prices[-8:] = [100.70, 100.62, 100.55, 100.58, 100.64, 100.72, 100.82, 100.94]
    volumes = [100.0] * 34 + [180.0]
    return pd.DataFrame({
        "time": list(range(35)), "open": prices, "high": prices,
        "low": prices, "close": prices, "volume": volumes,
    })


def exchange_candles():
    closed = signal_candles()
    live = closed.iloc[[-1]].copy()
    live["time"] = 35
    return pd.concat([closed, live], ignore_index=True)


class ScalpPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(
            scalp_paper, "DATABASE_PATH", os.path.join(self.temp.name, "scalp.db")
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_profiles_have_independent_risk(self):
        moderate = scalp_paper.PROFILES["scalp_5m"]
        aggressive = scalp_paper.PROFILES["scalp_aggressive_1m"]
        self.assertEqual(moderate["interval"], "5m")
        self.assertEqual(aggressive["interval"], "1m")
        self.assertGreater(aggressive["allocation"], moderate["allocation"])
        self.assertLess(aggressive["volume_ratio"], moderate["volume_ratio"])

    def test_start_and_stop_two_independent_profiles(self):
        first = scalp_paper.start_scalp_account("BTCUSDT", "scalp_5m", 100)
        second = scalp_paper.start_scalp_account("BTCUSDT", "scalp_aggressive_1m", 100)
        self.assertEqual(len(scalp_paper.get_active_scalp_accounts()), 2)
        scalp_paper.stop_scalp_account(first, 100)
        self.assertEqual(scalp_paper.get_scalp_dashboard("BTCUSDT", 100)[0]["id"], second)

    def test_signal_opens_and_target_closes_with_fees(self):
        account_id = scalp_paper.start_scalp_account("BTCUSDT", "scalp_aggressive_1m", 100)
        candles = exchange_candles()
        signal = scalp_paper.calculate_scalp_signal(candles.iloc[:-1], "scalp_aggressive_1m")
        self.assertTrue(signal["buy"], signal)
        opened = scalp_paper.evaluate_scalp_account(account_id, candles, 100.94)
        account = next(item for item in opened if item["id"] == account_id)
        self.assertGreater(account["quantity"], 0)
        closed = scalp_paper.evaluate_scalp_account(account_id, candles, account["target_price"])
        account = next(item for item in closed if item["id"] == account_id)
        self.assertEqual(account["quantity"], 0)
        self.assertGreater(account["stats"]["pnl"], 0)

    def test_duplicate_active_profile_is_rejected(self):
        scalp_paper.start_scalp_account("ETHUSDT", "scalp_5m", 50)
        with self.assertRaises(ValueError):
            scalp_paper.start_scalp_account("ETHUSDT", "scalp_5m", 50)


if __name__ == "__main__":
    unittest.main()
