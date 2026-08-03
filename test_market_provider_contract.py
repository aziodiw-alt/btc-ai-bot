import unittest
from unittest.mock import Mock, call, patch

from btc_terminal.market.legacy import LegacyMarketDataProvider
import market


class LegacyMarketDataProviderTest(unittest.TestCase):
    def test_bybit_provider_preserves_legacy_call_shape(self):
        ticker = Mock(return_value={"price": 100.0})
        klines = Mock(return_value="fixture-frame")
        provider = LegacyMarketDataProvider(
            "bybit",
            ticker_function=ticker,
            klines_function=klines,
        )

        self.assertEqual(provider.get_ticker("BTCUSDT"), {"price": 100.0})
        self.assertEqual(
            provider.get_klines("D", 250, "BTCUSDT"),
            "fixture-frame",
        )
        ticker.assert_called_once_with("BTCUSDT", exchange="bybit")
        klines.assert_called_once_with(
            "D",
            250,
            "BTCUSDT",
            exchange="bybit",
        )

    def test_exchange_normalization_matches_current_market_module(self):
        ticker = Mock(return_value={"price": 100.0})
        klines = Mock(return_value="fixture-frame")

        okx = LegacyMarketDataProvider(
            "OKX",
            ticker_function=ticker,
            klines_function=klines,
        )
        fallback = LegacyMarketDataProvider(
            "binance",
            ticker_function=ticker,
            klines_function=klines,
        )

        okx.get_ticker("ETHUSDT")
        fallback.get_ticker("ETHUSDT")

        self.assertEqual(okx.exchange, "okx")
        self.assertEqual(fallback.exchange, "bybit")
        self.assertEqual(
            ticker.call_args_list,
            [
                call("ETHUSDT", exchange="okx"),
                call("ETHUSDT", exchange="bybit"),
            ],
        )


class RootMarketCompatibilityTest(unittest.TestCase):
    @patch("market.OkxMarketDataProvider")
    @patch("market.BybitMarketDataProvider")
    def test_root_functions_dispatch_without_changing_call_shape(
        self,
        bybit_provider_class,
        okx_provider_class,
    ):
        bybit_provider_class.return_value.get_ticker.return_value = {
            "price": 100.0
        }
        okx_provider_class.return_value.get_klines.return_value = "okx-frame"

        ticker = market.get_ticker("BTCUSDT", exchange="binance")
        candles = market.get_klines(
            "D",
            250,
            "ETHUSDT",
            exchange="OKX",
        )

        self.assertEqual(ticker, {"price": 100.0})
        self.assertEqual(candles, "okx-frame")
        bybit_provider_class.assert_called_once_with()
        bybit_provider_class.return_value.get_ticker.assert_called_once_with(
            "BTCUSDT"
        )
        okx_provider_class.assert_called_once_with()
        okx_provider_class.return_value.get_klines.assert_called_once_with(
            "D",
            250,
            "ETHUSDT",
        )

    def test_private_normalizers_remain_compatible(self):
        self.assertEqual(market._normalize_exchange("OKX"), "okx")
        self.assertEqual(market._normalize_exchange("unknown"), "bybit")
        self.assertEqual(market._okx_symbol("BTCUSDT"), "BTC-USDC")
        self.assertEqual(market._okx_interval("D"), "1Dutc")


if __name__ == "__main__":
    unittest.main()
