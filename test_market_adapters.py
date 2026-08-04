import unittest
from unittest.mock import Mock

from btc_terminal.market.bybit import BybitMarketDataProvider
from btc_terminal.market.binance import (
    BinanceMarketDataProvider,
    normalize_binance_interval,
)
from btc_terminal.market.okx import (
    OkxMarketDataProvider,
    normalize_okx_interval,
    normalize_okx_symbol,
)


def response(payload):
    result = Mock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


class BybitMarketDataProviderTest(unittest.TestCase):
    def test_ticker_is_normalized_to_numeric_contract(self):
        session = Mock()
        session.get.return_value = response(
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "lastPrice": "100.5",
                            "highPrice24h": "110",
                            "lowPrice24h": "90",
                            "volume24h": "1234.5",
                        }
                    ]
                },
            }
        )
        provider = BybitMarketDataProvider("https://bybit.test", session)

        self.assertEqual(
            provider.get_ticker("BTCUSDT"),
            {"price": 100.5, "high": 110.0, "low": 90.0, "volume": 1234.5},
        )
        session.get.assert_called_once_with(
            "https://bybit.test/v5/market/tickers",
            params={"category": "spot", "symbol": "BTCUSDT"},
            timeout=10,
        )

    def test_candles_are_reversed_to_ascending_order(self):
        session = Mock()
        session.get.return_value = response(
            {
                "retCode": 0,
                "result": {
                    "list": [
                        ["2", "2", "3", "1", "2.5", "20", "50"],
                        ["1", "1", "2", "0.5", "1.5", "10", "15"],
                    ]
                },
            }
        )
        provider = BybitMarketDataProvider("https://bybit.test", session)

        frame = provider.get_klines("240", 250, "BTCUSDT")

        self.assertEqual(frame["time"].tolist(), ["1", "2"])
        self.assertEqual(frame["close"].tolist(), [1.5, 2.5])
        self.assertEqual(frame["volume"].tolist(), [10.0, 20.0])


class OkxMarketDataProviderTest(unittest.TestCase):
    def test_symbol_and_interval_mapping_match_current_behavior(self):
        self.assertEqual(normalize_okx_symbol("BTCUSDT"), "BTC-USDC")
        self.assertEqual(normalize_okx_symbol("eth/usdc"), "ETH-USDC")
        self.assertEqual(normalize_okx_interval("60"), "1H")
        self.assertEqual(normalize_okx_interval("240"), "4H")
        self.assertEqual(normalize_okx_interval("D"), "1Dutc")

    def test_ticker_and_candle_request_contract(self):
        session = Mock()
        session.get.side_effect = [
            response(
                {
                    "code": "0",
                    "data": [
                        {
                            "last": "100.5",
                            "high24h": "110",
                            "low24h": "90",
                            "vol24h": "1234.5",
                        }
                    ],
                }
            ),
            response(
                {
                    "code": "0",
                    "data": [
                        ["2", "2", "3", "1", "2.5", "20", "50", "1"],
                        ["1", "1", "2", "0.5", "1.5", "10", "15", "1"],
                    ],
                }
            ),
        ]
        provider = OkxMarketDataProvider("https://okx.test", session)

        ticker = provider.get_ticker("BTCUSDT")
        frame = provider.get_klines("D", 500, "BTCUSDT")

        self.assertEqual(
            ticker,
            {"price": 100.5, "high": 110.0, "low": 90.0, "volume": 1234.5},
        )
        self.assertEqual(frame["time"].tolist(), ["1", "2"])
        self.assertEqual(frame["close"].tolist(), [1.5, 2.5])
        self.assertEqual(
            session.get.call_args_list[1].kwargs["params"],
            {"instId": "BTC-USDC", "bar": "1Dutc", "limit": 300},
        )


class BinanceMarketDataProviderTest(unittest.TestCase):
    def test_ticker_and_candles_are_normalized(self):
        session = Mock()
        session.get.side_effect = [
            response({
                "lastPrice": "100.5", "highPrice": "110",
                "lowPrice": "90", "volume": "1234.5",
            }),
            response([
                [1, "1", "2", "0.5", "1.5", "10", "15"],
                [2, "2", "3", "1", "2.5", "20", "50"],
            ]),
        ]
        provider = BinanceMarketDataProvider("https://binance.test", session)

        self.assertEqual(normalize_binance_interval("240"), "4h")
        self.assertEqual(provider.get_ticker("BTCUSDT")["price"], 100.5)
        frame = provider.get_klines("D", 250, "BTCUSDT")
        self.assertEqual(frame["time"].tolist(), [1, 2])
        self.assertEqual(frame["close"].tolist(), [1.5, 2.5])


if __name__ == "__main__":
    unittest.main()
