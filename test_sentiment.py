import unittest
from unittest.mock import Mock, patch

from btc_terminal.market import sentiment


class SentimentProviderContractTest(unittest.TestCase):
    @patch("btc_terminal.market.sentiment.requests.get")
    def test_public_requests_preserve_bybit_parameters(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [
            {"retCode": 0, "result": {"list": [{"fundingRate": "0.0001"}]}},
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {"openInterest": "102"},
                        {"openInterest": "100"},
                    ]
                },
            },
            {
                "retCode": 0,
                "result": {
                    "list": [{"buyRatio": "0.55", "sellRatio": "0.45"}]
                },
            },
        ]
        get.return_value = response

        self.assertEqual(sentiment.get_funding("ETHUSDT"), 0.0001)
        self.assertEqual(sentiment.get_open_interest("ETHUSDT")["change_pct"], 2.0)
        self.assertAlmostEqual(
            sentiment.get_long_short("ETHUSDT")["ratio"],
            0.55 / 0.45,
        )
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args_list[0].kwargs["timeout"], 15)
        self.assertEqual(
            get.call_args_list[0].kwargs["params"],
            {"category": "linear", "symbol": "ETHUSDT", "limit": 2},
        )
        self.assertEqual(
            get.call_args_list[1].kwargs["params"]["intervalTime"],
            "4h",
        )
        self.assertEqual(get.call_args_list[2].kwargs["params"]["period"], "4h")

    @patch("btc_terminal.market.sentiment.get_long_short")
    @patch("btc_terminal.market.sentiment.get_open_interest")
    @patch("btc_terminal.market.sentiment.get_funding")
    def test_scoring_and_localized_messages_are_stable(
        self,
        get_funding,
        get_open_interest,
        get_long_short,
    ):
        get_funding.return_value = 0.0001
        get_open_interest.return_value = {
            "current": 102.0,
            "previous": 100.0,
            "change_pct": 2.0,
        }
        get_long_short.return_value = {
            "long_pct": 55.0,
            "short_pct": 45.0,
            "ratio": 55 / 45,
        }

        result = sentiment.get_sentiment("BTCUSDT")

        self.assertEqual(result["sentiment_score"], 30)
        self.assertEqual(
            result["reasons"],
            [
                "Funding нейтральный",
                "Long/Short без сильного перекоса",
                "Open Interest умеренно растет",
            ],
        )
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["funding_pct"], 0.01)


if __name__ == "__main__":
    unittest.main()
