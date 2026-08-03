import unittest
from unittest.mock import call, patch

from fast_strategy import analyze_fast_strategy
from test_strategy import indicator_values, sentiment_values, trade_levels


FAST_RESULT_KEYS = {
    "symbol",
    "exchange",
    "display_symbol",
    "asset",
    "strategy_key",
    "strategy_name",
    "strategy_description",
    "market_mode",
    "market_mode_label",
    "market_mode_description",
    "price",
    "support",
    "support_zone",
    "resistance",
    "distance_to_resistance_pct",
    "trend_score",
    "trend_max",
    "entry_score",
    "entry_max",
    "indicators_score",
    "indicators_max",
    "rsi_score",
    "rsi_max",
    "macd_score",
    "macd_max",
    "sentiment_score",
    "sentiment_max",
    "total_score",
    "score_max",
    "grade",
    "decision",
    "rsi_4h",
    "rsi_label",
    "funding_pct",
    "long_short_ratio",
    "open_interest_change_pct",
    "reasons",
    "warnings",
    "buy_zone_1",
    "buy_zone_2",
    "stop_loss",
    "take_profit_1",
    "take_profit_2",
    "planned_entry",
    "available_profit_pct",
    "target_15_20_available",
}


class FastStrategyContractTest(unittest.TestCase):
    @patch("btc_terminal.strategy.fast.calculate_trade_levels")
    @patch("btc_terminal.strategy.fast.calculate_support_resistance", return_value=(99.0, 102.0))
    @patch("btc_terminal.strategy.fast.detect_market_state")
    @patch("btc_terminal.strategy.fast.get_sentiment", return_value=sentiment_values())
    @patch("btc_terminal.strategy.fast.analyze")
    @patch("btc_terminal.strategy.fast.get_klines")
    @patch("btc_terminal.strategy.fast.get_ticker", return_value={"price": 100.0})
    def test_fast_contract_and_data_flow(
        self,
        get_ticker,
        get_klines,
        analyze,
        _get_sentiment,
        detect_market_state,
        calculate_support_resistance,
        calculate_trade_levels,
    ):
        four_hour_frame = object()
        one_hour_frame = object()
        get_klines.side_effect = [four_hour_frame, one_hour_frame]
        analyze.side_effect = [indicator_values(), indicator_values()]
        detect_market_state.return_value = {
            "key": "UPTREND",
            "label": "Uptrend",
            "description": "Fixture market state",
        }
        levels = trade_levels()
        levels["available_profit_pct"] = 1.0
        calculate_trade_levels.return_value = levels

        result = analyze_fast_strategy("ETHUSDT", exchange="bybit")

        self.assertEqual(set(result), FAST_RESULT_KEYS)
        self.assertEqual(result["strategy_key"], "fast")
        self.assertEqual(result["strategy_name"], "Fast")
        self.assertEqual(result["display_symbol"], "ETH/USDT")
        self.assertEqual(result["trend_score"], 35)
        self.assertEqual(result["entry_score"], 25)
        self.assertEqual(result["indicators_score"], 20)
        self.assertEqual(result["sentiment_score"], 20)
        self.assertEqual(result["total_score"], 100)
        self.assertEqual(result["grade"], "A+")
        self.assertTrue(result["target_15_20_available"])

        get_ticker.assert_called_once_with("ETHUSDT", exchange="bybit")
        self.assertEqual(
            get_klines.call_args_list,
            [
                call("240", 250, "ETHUSDT", exchange="bybit"),
                call("60", 250, "ETHUSDT", exchange="bybit"),
            ],
        )
        self.assertEqual(analyze.call_args_list, [call(four_hour_frame), call(one_hour_frame)])
        calculate_support_resistance.assert_called_once_with(one_hour_frame, lookback=80)
        calculate_trade_levels.assert_called_once_with(
            100.0,
            99.0,
            102.0,
            atr=4.0,
            profile="fast",
        )


if __name__ == "__main__":
    unittest.main()
