import importlib
import unittest
from pathlib import Path


class PackageBoundaryTest(unittest.TestCase):
    def test_target_packages_are_importable(self):
        for module_name in (
            "btc_terminal",
            "btc_terminal.core",
            "btc_terminal.market",
            "btc_terminal.strategy",
            "btc_terminal.storage",
            "btc_terminal.ai",
            "btc_terminal.telegram",
            "btc_terminal.web",
            "btc_terminal.application",
        ):
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_grade_constants_preserve_current_thresholds(self):
        constants = importlib.import_module("btc_terminal.core.constants")

        self.assertEqual(constants.GRADE_A_PLUS_MIN_SCORE, 85)
        self.assertEqual(constants.GRADE_A_MIN_SCORE, 75)
        self.assertEqual(constants.GRADE_B_MIN_SCORE, 65)
        self.assertEqual(constants.GRADE_C_MIN_SCORE, 50)
        self.assertEqual(constants.STRATEGY_CACHE_TTL_SECONDS, 60)
        self.assertEqual(constants.CANDLE_CACHE_TTL_SECONDS, 15)
        self.assertEqual(constants.AI_REPORT_CACHE_TTL_SECONDS, 600)
        self.assertEqual(constants.HISTORY_SNAPSHOT_INTERVAL_SECONDS, 900)

    def test_legacy_market_and_strategy_imports_still_resolve_to_root_files(self):
        market_module = importlib.import_module("market")
        strategy_module = importlib.import_module("strategy")
        project_root = Path(__file__).resolve().parent

        self.assertEqual(Path(market_module.__file__).resolve(), project_root / "market.py")
        self.assertEqual(
            Path(strategy_module.__file__).resolve(),
            project_root / "strategy.py",
        )

    def test_new_facades_reference_the_exact_legacy_functions(self):
        legacy_market = importlib.import_module("market")
        legacy_sentiment = importlib.import_module("sentiment")
        legacy_indicators = importlib.import_module("indicators")
        legacy_levels = importlib.import_module("levels")
        legacy_market_state = importlib.import_module("market_state")
        legacy_swing = importlib.import_module("strategy")
        legacy_fast = importlib.import_module("fast_strategy")
        legacy_alpha = importlib.import_module("alpha_strategy")

        public_market = importlib.import_module("btc_terminal.market.public")
        sentiment = importlib.import_module("btc_terminal.market.sentiment")
        indicators = importlib.import_module("btc_terminal.strategy.indicators")
        levels = importlib.import_module("btc_terminal.strategy.levels")
        market_state = importlib.import_module("btc_terminal.strategy.market_state")
        swing = importlib.import_module("btc_terminal.strategy.swing")
        fast = importlib.import_module("btc_terminal.strategy.fast")
        alpha = importlib.import_module("btc_terminal.strategy.alpha")

        self.assertIs(public_market.get_ticker, legacy_market.get_ticker)
        self.assertIs(public_market.get_klines, legacy_market.get_klines)
        self.assertIs(sentiment.get_sentiment, legacy_sentiment.get_sentiment)
        self.assertIs(indicators.analyze, legacy_indicators.analyze)
        self.assertIs(
            levels.calculate_support_resistance,
            legacy_levels.calculate_support_resistance,
        )
        self.assertIs(
            levels.calculate_trade_levels,
            legacy_levels.calculate_trade_levels,
        )
        self.assertIs(
            market_state.detect_market_state,
            legacy_market_state.detect_market_state,
        )
        self.assertIs(swing.analyze_strategy, legacy_swing.analyze_strategy)
        self.assertIs(fast.analyze_fast_strategy, legacy_fast.analyze_fast_strategy)
        self.assertIs(
            alpha.analyze_alpha_strategy,
            legacy_alpha.analyze_alpha_strategy,
        )

    def test_dashboard_history_legacy_import_aliases_storage_module(self):
        legacy_history = importlib.import_module("dashboard_history")
        storage_history = importlib.import_module("btc_terminal.storage.history")

        self.assertIs(legacy_history, storage_history)

    def test_dashboard_trade_calculations_use_application_functions(self):
        legacy_trades = importlib.import_module("dashboard_trades")
        calculations = importlib.import_module(
            "btc_terminal.application.trades"
        )

        self.assertIs(
            legacy_trades.calculate_sell_advice,
            calculations.calculate_sell_advice,
        )
        self.assertIs(
            legacy_trades.calculate_okx_fifo_statistics,
            calculations.calculate_okx_fifo_statistics,
        )
        self.assertIs(
            legacy_trades.add_okx_order_profit_estimates,
            calculations.add_okx_order_profit_estimates,
        )
        self.assertIs(
            legacy_trades.classify_order_strategy,
            calculations.classify_order_strategy,
        )

    def test_dashboard_trade_module_aliases_storage_repository(self):
        legacy_trades = importlib.import_module("dashboard_trades")
        web_trades = importlib.import_module("web.dashboard_trades")
        storage_trades = importlib.import_module(
            "btc_terminal.storage.trades"
        )

        self.assertIs(legacy_trades, storage_trades)
        self.assertIs(web_trades, storage_trades)

    def test_telegram_storage_facade_uses_legacy_repository_functions(self):
        legacy_database = importlib.import_module("database")
        telegram_storage = importlib.import_module(
            "btc_terminal.storage.telegram"
        )

        self.assertIs(
            telegram_storage.init_database,
            legacy_database.init_database,
        )
        self.assertIs(
            telegram_storage.get_bybit_fifo_statistics,
            legacy_database.get_bybit_fifo_statistics,
        )
        self.assertIs(
            telegram_storage.get_signal_subscribers,
            legacy_database.get_signal_subscribers,
        )

    def test_bot_formatters_use_telegram_package_functions(self):
        bot = importlib.import_module("bot")
        formatting = importlib.import_module(
            "btc_terminal.telegram.formatting"
        )

        self.assertIs(bot.format_number, formatting.format_number)
        self.assertIs(bot.format_zone, formatting.format_zone)
        self.assertIs(bot.format_analysis, formatting.format_analysis)


if __name__ == "__main__":
    unittest.main()
