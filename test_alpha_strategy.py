import unittest
from unittest.mock import call, patch

import pandas as pd

from alpha_strategy import (
    _avoid_round_number,
    analyze_alpha_strategy,
    calculate_alpha_levels,
)
from test_strategy import indicator_values, sentiment_values


class AlphaStrategyContractTest(unittest.TestCase):
    def test_entries_are_below_price_staggered_and_fully_allocated(self):
        result = calculate_alpha_levels(
            price=65000,
            support=62500,
            resistance=67000,
            atr=800,
            symbol="BTCUSDT",
        )

        self.assertLess(result["buy_zone_1"][1], 65000)
        self.assertLess(result["buy_zone_2"][1], result["buy_zone_1"][0])
        self.assertEqual(
            [item["allocation_pct"] for item in result["entry_plan"]],
            [20, 30, 50],
        )
        self.assertEqual(
            sum(item["allocation_pct"] for item in result["entry_plan"]),
            100,
        )
        self.assertTrue(result["trailing_stop"]["enabled_after_profit"])
        self.assertGreater(
            result["trailing_stop"]["protected_stop"],
            result["planned_entry"],
        )

    def test_round_number_buffer_is_preserved(self):
        self.assertEqual(_avoid_round_number(65005, "BTCUSDT"), 64983.0)
        self.assertNotEqual(_avoid_round_number(65000, "BTCUSDT") % 100, 0)

    @patch(
        "btc_terminal.strategy.alpha.calculate_support_resistance",
        return_value=(95.0, 110.0),
    )
    @patch("btc_terminal.strategy.alpha.get_sentiment")
    @patch("btc_terminal.strategy.alpha.analyze")
    @patch("btc_terminal.strategy.alpha.get_klines")
    @patch(
        "btc_terminal.strategy.alpha.get_ticker",
        return_value={"price": 100.0},
    )
    def test_full_alpha_contract_and_exchange_data_flow(
        self,
        get_ticker,
        get_klines,
        analyze,
        get_sentiment,
        _calculate_support_resistance,
    ):
        daily_frame = pd.DataFrame({"close": [98.0, 99.0, 99.5, 100.0]})
        four_hour_frame = pd.DataFrame(
            {"close": [98.0, 99.0, 99.5, 100.0]}
        )
        get_klines.side_effect = [daily_frame, four_hour_frame]
        analyze.side_effect = [indicator_values(), indicator_values()]
        get_sentiment.return_value = sentiment_values()

        result = analyze_alpha_strategy("BTCUSDT", exchange="okx")

        self.assertEqual(result["strategy_key"], "alpha")
        self.assertEqual(result["strategy_name"], "Alpha")
        self.assertEqual(result["exchange"], "okx")
        self.assertEqual(result["display_symbol"], "BTC/USD (USDC)")
        self.assertEqual(result["total_score"], 95)
        self.assertEqual(result["grade"], "A+")
        self.assertEqual(result["entry_status"], "WAIT_PULLBACK")
        self.assertEqual(
            [item["allocation_pct"] for item in result["entry_plan"]],
            [20, 30, 50],
        )
        get_ticker.assert_called_once_with("BTCUSDT", exchange="okx")
        self.assertEqual(
            get_klines.call_args_list,
            [
                call("D", 250, "BTCUSDT", exchange="okx"),
                call("240", 250, "BTCUSDT", exchange="okx"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
