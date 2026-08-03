import unittest
from unittest.mock import patch
from pathlib import Path
import sys
import base64
import types

import pandas as pd

WEB_DIR = Path(__file__).resolve().parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from web import app as web_app


class DashboardAnalysisContractTest(unittest.TestCase):
    def setUp(self):
        self.original_username = web_app.DASHBOARD_USERNAME
        self.original_password = web_app.DASHBOARD_PASSWORD
        web_app.DASHBOARD_USERNAME = "fixture-user"
        web_app.DASHBOARD_PASSWORD = "fixture-password"
        self.client = web_app.app.test_client()
        with web_app._cache_lock:
            web_app._strategy_cache.clear()
            web_app._candle_cache.clear()
        with web_app._ai_cache_lock:
            web_app._ai_cache.update(
                {
                    "signature": None,
                    "created_at": 0.0,
                    "value": None,
                }
            )

    def tearDown(self):
        web_app.DASHBOARD_USERNAME = self.original_username
        web_app.DASHBOARD_PASSWORD = self.original_password

    def auth_headers(self, username="fixture-user", password="fixture-password"):
        credentials = base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        return {"Authorization": f"Basic {credentials}"}

    def test_health_check_bypasses_dashboard_authentication(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_protected_route_rejects_missing_or_invalid_credentials(self):
        missing = self.client.get("/api/chart-data")
        invalid = self.client.get(
            "/api/chart-data",
            headers=self.auth_headers(password="wrong"),
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertIn("Basic", missing.headers["WWW-Authenticate"])

    def test_protected_route_returns_503_when_login_is_not_configured(self):
        web_app.DASHBOARD_USERNAME = None
        web_app.DASHBOARD_PASSWORD = None

        response = self.client.get("/api/chart-data")

        self.assertEqual(response.status_code, 503)

    def test_chart_data_rejects_unsupported_timeframe(self):
        response = self.client.get(
            "/api/chart-data?timeframe=15",
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    @patch("web.app._get_cached_strategy")
    @patch("web.app._get_cached_candles")
    def test_chart_data_response_and_parameter_fallbacks(
        self,
        get_cached_candles,
        get_cached_strategy,
    ):
        get_cached_candles.return_value = [
            {"time": 1, "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0}
        ]
        get_cached_strategy.return_value = {
            "price": 105.0,
            "support": 90.0,
            "support_zone": [89.0, 91.0],
            "resistance": 110.0,
            "buy_zone_1": [98.0, 99.0],
            "buy_zone_2": [95.0, 96.0],
            "stop_loss": 94.0,
            "take_profit_1": 108.0,
            "take_profit_2": 109.0,
        }

        response = self.client.get(
            "/api/chart-data?timeframe=D&symbol=SOLUSDT&strategy=alpha&exchange=binance",
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["exchange"], "bybit")
        self.assertEqual(payload["display_symbol"], "BTC/USDT")
        self.assertEqual(payload["timeframe"], "D")
        self.assertEqual(payload["timeframe_label"], "1D")
        self.assertEqual(payload["levels"]["current_price"], 105.0)
        self.assertEqual(payload["levels"]["support_zone"], [89.0, 91.0])
        get_cached_candles.assert_called_once_with("D", "BTCUSDT", "bybit")
        get_cached_strategy.assert_called_once_with("alpha", "BTCUSDT", "bybit")

    @patch("web.app._ai_report_service.news_loader")
    @patch("web.app._ai_report_service.whale_loader")
    @patch("web.app._ai_report_service.strategy_loader")
    def test_ai_report_is_generated_once_then_served_from_cache(
        self,
        get_cached_strategy,
        get_whale_context,
        get_news_context,
    ):
        strategy_result = {
            "price": 100.0,
            "total_score": 75,
            "grade": "A",
            "decision": "FIXTURE DECISION",
        }
        whale_context = {
            "score": 1,
            "events": [{"url": "https://example.test/whale"}],
        }
        news_context = {
            "score": -1,
            "articles": [{"url": "https://example.test/news"}],
        }
        get_cached_strategy.return_value = strategy_result
        get_whale_context.return_value = whale_context
        get_news_context.return_value = news_context

        generate_calls = []

        def generate_report(result, whale_context=None, news_context=None):
            generate_calls.append((result, whale_context, news_context))
            return "FIXTURE AI REPORT"

        fake_ai_module = types.SimpleNamespace(generate_report=generate_report)
        with patch.dict(sys.modules, {"ai_report": fake_ai_module}):
            first = self.client.post(
                "/api/ai-report?symbol=ETHUSDT&strategy=fast&exchange=okx",
                headers=self.auth_headers(),
            )
            second = self.client.post(
                "/api/ai-report?symbol=ETHUSDT&strategy=fast&exchange=okx",
                headers=self.auth_headers(),
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.get_json(),
            {"report": "FIXTURE AI REPORT", "cached": False},
        )
        self.assertEqual(
            second.get_json(),
            {"report": "FIXTURE AI REPORT", "cached": True},
        )
        self.assertEqual(len(generate_calls), 1)
        self.assertEqual(
            generate_calls[0],
            (strategy_result, whale_context, news_context),
        )
        get_cached_strategy.assert_called_with("fast", "ETHUSDT")

    @patch("web.app._ai_report_service.news_loader", return_value={"score": 0, "articles": []})
    @patch("web.app._ai_report_service.whale_loader", return_value={"score": 0, "events": []})
    @patch("web.app._ai_report_service.strategy_loader")
    def test_ai_report_cache_is_invalidated_by_strategy_signature(
        self,
        get_cached_strategy,
        _get_whale_context,
        _get_news_context,
    ):
        get_cached_strategy.side_effect = [
            {
                "price": 100.0,
                "total_score": 74,
                "grade": "B",
                "decision": "FIRST",
            },
            {
                "price": 101.0,
                "total_score": 75,
                "grade": "A",
                "decision": "SECOND",
            },
        ]
        generated_reports = iter(["REPORT ONE", "REPORT TWO"])
        fake_ai_module = types.SimpleNamespace(
            generate_report=lambda *_args, **_kwargs: next(generated_reports)
        )

        with patch.dict(sys.modules, {"ai_report": fake_ai_module}):
            first = self.client.post(
                "/api/ai-report",
                headers=self.auth_headers(),
            )
            second = self.client.post(
                "/api/ai-report",
                headers=self.auth_headers(),
            )

        self.assertEqual(first.get_json()["report"], "REPORT ONE")
        self.assertFalse(first.get_json()["cached"])
        self.assertEqual(second.get_json()["report"], "REPORT TWO")
        self.assertFalse(second.get_json()["cached"])

    def test_request_values_are_normalized_to_supported_options(self):
        self.assertEqual(web_app._normalize_strategy_name("FAST"), "fast")
        self.assertEqual(web_app._normalize_strategy_name("alpha"), "alpha")
        self.assertEqual(web_app._normalize_symbol("eth/usdt"), "ETHUSDT")
        self.assertEqual(web_app._normalize_symbol("SOLUSDT"), "BTCUSDT")
        self.assertEqual(web_app._normalize_exchange("OKX"), "okx")
        self.assertEqual(web_app._normalize_exchange("binance"), "bybit")

    @patch("web.app._analysis_service.snapshot_callback")
    @patch("web.app._analysis_service.fast_analyzer")
    @patch("web.app._analysis_service.swing_analyzer")
    def test_swing_result_is_cached_and_receives_dashboard_defaults(
        self,
        analyze_strategy,
        analyze_fast_strategy,
        save_snapshot_if_due,
    ):
        source_result = {
            "symbol": "BTCUSDT",
            "exchange": "bybit",
        }
        analyze_strategy.return_value = source_result

        first = web_app._get_cached_strategy("swing", "BTCUSDT", "bybit")
        second = web_app._get_cached_strategy("swing", "BTCUSDT", "bybit")

        self.assertIs(first, second)
        analyze_strategy.assert_called_once_with("BTCUSDT", exchange="bybit")
        analyze_fast_strategy.assert_not_called()
        save_snapshot_if_due.assert_called_once_with(first)
        self.assertEqual(first["strategy_key"], "swing")
        self.assertEqual(first["strategy_name"], "Swing")
        self.assertEqual(first["trend_max"], 40)
        self.assertEqual(first["entry_max"], 20)
        self.assertEqual(first["indicators_max"], 10)
        self.assertEqual(first["sentiment_max"], 30)

    @patch("web.app._analysis_service.snapshot_callback")
    @patch("web.app._analysis_service.fast_analyzer")
    @patch("web.app._analysis_service.swing_analyzer")
    def test_cache_key_separates_exchange_symbol_and_strategy(
        self,
        analyze_strategy,
        analyze_fast_strategy,
        save_snapshot_if_due,
    ):
        analyze_strategy.side_effect = lambda symbol, exchange: {
            "source": f"swing:{exchange}:{symbol}"
        }
        analyze_fast_strategy.side_effect = lambda symbol, exchange: {
            "source": f"fast:{exchange}:{symbol}"
        }

        results = (
            web_app._get_cached_strategy("swing", "BTCUSDT", "bybit"),
            web_app._get_cached_strategy("swing", "ETHUSDT", "bybit"),
            web_app._get_cached_strategy("swing", "BTCUSDT", "okx"),
            web_app._get_cached_strategy("fast", "BTCUSDT", "bybit"),
        )

        self.assertEqual(
            [result["source"] for result in results],
            [
                "swing:bybit:BTCUSDT",
                "swing:bybit:ETHUSDT",
                "swing:okx:BTCUSDT",
                "fast:bybit:BTCUSDT",
            ],
        )
        self.assertEqual(analyze_strategy.call_count, 3)
        self.assertEqual(analyze_fast_strategy.call_count, 1)
        self.assertEqual(save_snapshot_if_due.call_count, 4)

    @patch("web.app.get_klines")
    def test_candles_are_serialized_and_cached(self, get_klines):
        get_klines.return_value = pd.DataFrame(
            [
                {
                    "time": 1_700_000_000_000,
                    "open": 100,
                    "high": 110,
                    "low": 90,
                    "close": 105,
                    "volume": 12,
                    "turnover": 1200,
                },
                {
                    "time": 1_700_000_060_000,
                    "open": 105,
                    "high": 115,
                    "low": 100,
                    "close": 112,
                    "volume": 15,
                    "turnover": 1600,
                },
            ]
        )

        first = web_app._get_cached_candles("60", "ETHUSDT", "okx")
        second = web_app._get_cached_candles("60", "ETHUSDT", "okx")

        self.assertIs(first, second)
        get_klines.assert_called_once_with(
            "60",
            250,
            "ETHUSDT",
            exchange="okx",
        )
        self.assertEqual(
            first,
            [
                {
                    "time": 1_700_000_000,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 105.0,
                },
                {
                    "time": 1_700_000_060,
                    "open": 105.0,
                    "high": 115.0,
                    "low": 100.0,
                    "close": 112.0,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
