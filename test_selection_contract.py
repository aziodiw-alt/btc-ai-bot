import unittest

from btc_terminal.application.selection import (
    SUPPORTED_ANALYSIS_SYMBOLS,
    normalize_exchange,
    normalize_strategy_name,
    normalize_symbol,
)


class AnalysisSelectionContractTest(unittest.TestCase):
    def test_strategy_selection_supports_three_explicit_profiles(self):
        self.assertEqual(normalize_strategy_name("FAST"), "fast")
        self.assertEqual(normalize_strategy_name("swing"), "swing")
        self.assertEqual(normalize_strategy_name("alpha"), "alpha")
        self.assertEqual(normalize_strategy_name(None), "swing")

    def test_symbol_selection_preserves_current_allowlist_and_fallback(self):
        self.assertEqual(SUPPORTED_ANALYSIS_SYMBOLS, {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(normalize_symbol("eth/usdt"), "ETHUSDT")
        self.assertEqual(normalize_symbol("BTCUSDT"), "BTCUSDT")
        self.assertEqual(normalize_symbol("SOLUSDT"), "BTCUSDT")
        self.assertEqual(normalize_symbol(None), "BTCUSDT")

    def test_exchange_selection_preserves_current_fallback(self):
        self.assertEqual(normalize_exchange(" OKX "), "okx")
        self.assertEqual(normalize_exchange("BYBIT"), "bybit")
        self.assertEqual(normalize_exchange("binance"), "bybit")
        self.assertEqual(normalize_exchange(None), "bybit")


if __name__ == "__main__":
    unittest.main()
