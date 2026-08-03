import unittest
from unittest.mock import call, patch

from strategy import analyze_strategy


SWING_RESULT_KEYS = {
    "symbol",
    "exchange",
    "display_symbol",
    "asset",
    "strategy_key",
    "strategy_name",
    "market_mode",
    "market_mode_label",
    "market_mode_description",
    "price",
    "support",
    "support_zone",
    "resistance",
    "distance_to_resistance_pct",
    "trend_score",
    "entry_score",
    "indicators_score",
    "rsi_score",
    "macd_score",
    "sentiment_score",
    "total_score",
    "score_max",
    "grade",
    "decision",
    "rsi_4h",
    "macd_4h",
    "macd_signal_4h",
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


def indicator_values():
    return {
        "rsi": 50.0,
        "ema20": 100.0,
        "ema50": 95.0,
        "ema200": 90.0,
        "macd": 2.0,
        "macd_signal": 1.0,
        "macd_histogram": 1.0,
        "macd_histogram_previous": 0.5,
        "atr": 4.0,
    }


def sentiment_values(score=30):
    return {
        "sentiment_score": score,
        "funding_pct": 0.01,
        "long_short_ratio": 1.1,
        "open_interest_change_pct": 2.0,
        "reasons": ["sentiment reason"],
        "warnings": ["sentiment warning"],
    }


def trade_levels(target_available=True):
    return {
        "buy_zone_1": [98.0, 99.0],
        "buy_zone_2": [96.0, 97.0],
        "support_zone": [98.0, 100.0],
        "stop_loss": 95.0,
        "take_profit_1": 105.0,
        "take_profit_2": 107.0,
        "planned_entry": 99.0,
        "safe_resistance": 109.0,
        "available_profit_pct": 10.1,
        "target_available": target_available,
    }


class SwingStrategyContractTest(unittest.TestCase):
    @patch("btc_terminal.strategy.swing.calculate_trade_levels")
    @patch("btc_terminal.strategy.swing.calculate_support_resistance", return_value=(95.0, 110.0))
    @patch("btc_terminal.strategy.swing.detect_market_state")
    @patch("btc_terminal.strategy.swing.get_sentiment")
    @patch("btc_terminal.strategy.swing.analyze")
    @patch("btc_terminal.strategy.swing.get_klines")
    @patch("btc_terminal.strategy.swing.get_ticker", return_value={"price": 100.0})
    def test_swing_contract_and_data_flow(
        self,
        get_ticker,
        get_klines,
        analyze,
        get_sentiment,
        detect_market_state,
        calculate_support_resistance,
        calculate_trade_levels,
    ):
        daily_frame = object()
        four_hour_frame = object()
        get_klines.side_effect = [daily_frame, four_hour_frame]
        analyze.side_effect = [indicator_values(), indicator_values()]
        get_sentiment.return_value = sentiment_values()
        detect_market_state.return_value = {
            "key": "UPTREND",
            "label": "Uptrend",
            "description": "Fixture market state",
        }
        calculate_trade_levels.return_value = trade_levels()

        result = analyze_strategy("BTCUSDT", exchange="okx")

        self.assertEqual(set(result), SWING_RESULT_KEYS)
        self.assertEqual(result["strategy_key"], "swing")
        self.assertEqual(result["strategy_name"], "Swing")
        self.assertEqual(result["exchange"], "okx")
        self.assertEqual(result["display_symbol"], "BTC/USD (USDC)")
        self.assertEqual(result["market_mode"], "UPTREND")
        self.assertEqual(result["trend_score"], 40)
        self.assertEqual(result["entry_score"], 15)
        self.assertEqual(result["indicators_score"], 10)
        self.assertEqual(result["sentiment_score"], 30)
        self.assertEqual(result["total_score"], 95)
        self.assertEqual(result["grade"], "A+")
        self.assertTrue(result["target_15_20_available"])

        get_ticker.assert_called_once_with("BTCUSDT", exchange="okx")
        self.assertEqual(
            get_klines.call_args_list,
            [
                call("D", 250, "BTCUSDT", exchange="okx"),
                call("240", 250, "BTCUSDT", exchange="okx"),
            ],
        )
        self.assertEqual(analyze.call_args_list, [call(daily_frame), call(four_hour_frame)])
        calculate_support_resistance.assert_called_once_with(four_hour_frame)
        calculate_trade_levels.assert_called_once_with(
            100.0,
            95.0,
            110.0,
            atr=4.0,
            profile="swing",
        )

    @patch("btc_terminal.strategy.swing.calculate_trade_levels")
    @patch("btc_terminal.strategy.swing.calculate_support_resistance", return_value=(95.0, 110.0))
    @patch("btc_terminal.strategy.swing.detect_market_state")
    @patch("btc_terminal.strategy.swing.get_sentiment", return_value=sentiment_values())
    @patch("btc_terminal.strategy.swing.analyze", side_effect=[indicator_values(), indicator_values()])
    @patch("btc_terminal.strategy.swing.get_klines", side_effect=[object(), object()])
    @patch("btc_terminal.strategy.swing.get_ticker", return_value={"price": 100.0})
    def test_safe_target_gate_downgrades_buy_grade(
        self,
        _get_ticker,
        _get_klines,
        _analyze,
        _get_sentiment,
        detect_market_state,
        _calculate_support_resistance,
        calculate_trade_levels,
    ):
        detect_market_state.return_value = {
            "key": "UPTREND",
            "label": "Uptrend",
            "description": "Fixture market state",
        }
        calculate_trade_levels.return_value = trade_levels(target_available=False)

        result = analyze_strategy()

        self.assertEqual(result["total_score"], 95)
        self.assertEqual(result["grade"], "B")
        self.assertFalse(result["target_15_20_available"])

    @patch("btc_terminal.strategy.swing.calculate_trade_levels", return_value=trade_levels())
    @patch("btc_terminal.strategy.swing.calculate_support_resistance", return_value=(95.0, 110.0))
    @patch("btc_terminal.strategy.swing.detect_market_state")
    @patch("btc_terminal.strategy.swing.get_sentiment")
    @patch("btc_terminal.strategy.swing.analyze")
    @patch("btc_terminal.strategy.swing.get_klines", side_effect=[object(), object()] * 5)
    @patch("btc_terminal.strategy.swing.get_ticker", return_value={"price": 100.0})
    def test_grade_boundaries_are_stable(
        self,
        _get_ticker,
        _get_klines,
        analyze,
        get_sentiment,
        detect_market_state,
        _calculate_support_resistance,
        _calculate_trade_levels,
    ):
        detect_market_state.return_value = {
            "key": "UPTREND",
            "label": "Uptrend",
            "description": "Fixture market state",
        }
        cases = (
            (20, 85, "A+"),
            (10, 75, "A"),
            (0, 65, "B"),
            (-15, 50, "C"),
            (-16, 49, "SKIP"),
        )

        for sentiment_score, total_score, grade in cases:
            with self.subTest(total_score=total_score, grade=grade):
                analyze.side_effect = [indicator_values(), indicator_values()]
                get_sentiment.return_value = sentiment_values(sentiment_score)

                result = analyze_strategy()

                self.assertEqual(result["total_score"], total_score)
                self.assertEqual(result["grade"], grade)

    @patch("btc_terminal.strategy.swing.calculate_trade_levels", return_value=trade_levels())
    @patch("btc_terminal.strategy.swing.calculate_support_resistance", return_value=(95.0, 110.0))
    @patch("btc_terminal.strategy.swing.detect_market_state")
    @patch("btc_terminal.strategy.swing.get_sentiment", return_value=sentiment_values())
    @patch("btc_terminal.strategy.swing.analyze", side_effect=[indicator_values(), indicator_values()])
    @patch("btc_terminal.strategy.swing.get_klines", side_effect=[object(), object()])
    @patch("btc_terminal.strategy.swing.get_ticker", return_value={"price": 100.0})
    def test_downtrend_overrides_high_score(
        self,
        _get_ticker,
        _get_klines,
        _analyze,
        _get_sentiment,
        detect_market_state,
        _calculate_support_resistance,
        _calculate_trade_levels,
    ):
        detect_market_state.return_value = {
            "key": "DOWNTREND",
            "label": "Downtrend",
            "description": "Fixture market state",
        }

        result = analyze_strategy()

        self.assertEqual(result["total_score"], 95)
        self.assertEqual(result["grade"], "SKIP")


if __name__ == "__main__":
    unittest.main()
