import unittest

import bot
from bot import (
    format_analysis,
    format_manual_wallet,
    format_number,
    format_zone,
)


class TelegramFormattingContractTest(unittest.TestCase):
    def test_number_and_zone_formatting(self):
        self.assertEqual(format_number(12345.67), "12 346")
        self.assertEqual(format_number(12345.67, 2), "12 345.67")
        self.assertIn("9 500", format_zone([10_000, 9_500]))
        self.assertIn("10 000", format_zone([10_000, 9_500]))

    def test_analysis_contains_current_public_fields(self):
        result = {
            "display_symbol": "ETH/USD (USDC)",
            "exchange": "okx",
            "price": 2345.67,
            "market_mode_label": "Fixture mode",
            "trend_score": 40,
            "entry_score": 20,
            "indicators_score": 10,
            "sentiment_score": 30,
            "total_score": 100,
            "grade": "A+",
            "decision": "FIXTURE DECISION",
            "buy_zone_1": [2300, 2310],
            "buy_zone_2": [2250, 2260],
            "stop_loss": 2200,
            "take_profit_1": 2400,
            "take_profit_2": 2450,
            "reasons": ["first reason", "second reason"],
            "warnings": ["first warning"],
        }

        message = format_analysis(result)

        self.assertEqual(message, bot._legacy_format_analysis(result))

        for expected_text in (
            "ETH/USD (USDC)",
            "OKX",
            "2 345.67",
            "Fixture mode",
            "40/40",
            "20/20",
            "10/10",
            "30/30",
            "100/100",
            "A+",
            "FIXTURE DECISION",
            "first reason",
            "second reason",
            "first warning",
        ):
            with self.subTest(expected_text=expected_text):
                self.assertIn(expected_text, message)

    def test_manual_wallet_message_is_explicitly_not_live(self):
        message = format_manual_wallet(
            {
                "btc": 0.01,
                "eth": 0.5,
                "usdt": 100,
                "updated_at": "2026-08-04T10:00:00+00:00",
            }
        )

        self.assertIn("0.01000000", message)
        self.assertIn("0.50000000", message)
        self.assertIn("100.00", message)
        self.assertIn("не онлайн-баланс", message)


if __name__ == "__main__":
    unittest.main()
