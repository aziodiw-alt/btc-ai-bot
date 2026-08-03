import unittest
from unittest.mock import Mock

from btc_terminal.application.analysis import AnalysisService


class AnalysisServiceContractTest(unittest.TestCase):
    def test_cache_expiry_and_normalized_dispatch(self):
        swing = Mock(side_effect=[{"source": "swing"}, {"source": "swing"}])
        fast = Mock(return_value={"source": "fast"})
        snapshot = Mock()
        times = iter([0, 0, 5, 11, 11])
        service = AnalysisService(
            swing,
            fast,
            snapshot,
            cache_ttl=10,
            clock=lambda: next(times),
        )

        first = service.analyze("unknown", "SOLUSDT", "binance")
        cached = service.analyze("swing", "BTCUSDT", "bybit")
        refreshed = service.analyze("swing", "BTCUSDT", "bybit")

        self.assertIs(first, cached)
        self.assertIsNot(first, refreshed)
        self.assertEqual(swing.call_count, 2)
        swing.assert_called_with("BTCUSDT", exchange="bybit")
        fast.assert_not_called()
        self.assertEqual(snapshot.call_count, 2)

    def test_fast_dispatch_does_not_add_swing_defaults(self):
        swing = Mock()
        fast = Mock(return_value={"source": "fast"})
        service = AnalysisService(swing, fast, Mock())

        result = service.analyze("fast", "ETHUSDT", "okx")

        self.assertEqual(result, {"source": "fast"})
        fast.assert_called_once_with("ETHUSDT", exchange="okx")

    def test_alpha_dispatch_uses_dedicated_analyzer(self):
        swing = Mock()
        fast = Mock()
        alpha = Mock(return_value={"source": "alpha"})
        snapshot = Mock()
        service = AnalysisService(
            swing,
            fast,
            snapshot,
            alpha_analyzer=alpha,
        )

        result = service.analyze("ALPHA", "BTCUSDT", "okx")

        self.assertEqual(result, {"source": "alpha"})
        alpha.assert_called_once_with("BTCUSDT", exchange="okx")
        swing.assert_not_called()
        fast.assert_not_called()
        snapshot.assert_called_once_with(result)


if __name__ == "__main__":
    unittest.main()
