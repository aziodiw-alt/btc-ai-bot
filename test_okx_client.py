import unittest
import sys
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from okx_client import OkxReadOnlyClient


class OkxReadOnlyClientTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.client = OkxReadOnlyClient(
            api_key="key",
            api_secret="secret",
            passphrase="passphrase",
            base_url="https://eea.okx.com",
            session=self.session,
        )

    def _response(self, payload):
        response = Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    def test_status_reads_permissions_and_nonzero_balances(self):
        self.session.get.side_effect = [
            self._response(
                {
                    "code": "0",
                    "data": [{"perm": "read_only", "acctLv": "1"}],
                }
            ),
            self._response(
                {
                    "code": "0",
                    "data": [
                        {
                            "details": [
                                {
                                    "ccy": "BTC",
                                    "eq": "0.01",
                                    "availBal": "0.009",
                                },
                                {
                                    "ccy": "ETH",
                                    "eq": "0",
                                    "availBal": "0",
                                },
                            ]
                        }
                    ],
                }
            ),
        ]

        status = self.client.connection_status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["permission"], "read_only")
        self.assertEqual(len(status["currencies"]), 1)
        self.assertEqual(status["currencies"][0]["currency"], "BTC")

    def test_api_error_does_not_include_credentials(self):
        self.session.get.return_value = self._response(
            {"code": "50111", "msg": "Invalid key"}
        )

        with self.assertRaisesRegex(RuntimeError, "Invalid key"):
            self.client.get_account_config()

    def test_open_spot_orders_are_normalized(self):
        self.session.get.return_value = self._response(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "123",
                        "instId": "BTC-USDT",
                        "side": "buy",
                        "ordType": "limit",
                        "px": "62000",
                        "sz": "0.01",
                        "accFillSz": "0.002",
                        "state": "partially_filled",
                        "cTime": "1700000000000",
                    }
                ],
            }
        )

        orders = self.client.get_open_orders()

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["side"], "BUY")
        self.assertAlmostEqual(orders[0]["remaining_size"], 0.008)
        self.assertAlmostEqual(orders[0]["remaining_value"], 496)
        requested_url = self.session.get.call_args.args[0]
        self.assertIn("orders-pending?instType=SPOT", requested_url)

    def test_spot_trade_history_is_normalized(self):
        self.session.get.return_value = self._response(
            {
                "code": "0",
                "data": [
                    {
                        "tradeId": "trade-1",
                        "ordId": "order-1",
                        "instId": "BTC-USDT",
                        "side": "buy",
                        "fillPx": "64000",
                        "fillSz": "0.001",
                        "fee": "-0.000001",
                        "feeCcy": "BTC",
                        "fillTime": "1720000000000",
                    }
                ],
            }
        )

        trades = self.client.get_trade_history()

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "BUY")
        self.assertEqual(trades[0]["value"], 64.0)
        self.assertEqual(trades[0]["fee_currency"], "BTC")
        requested_url = self.session.get.call_args.args[0]
        self.assertIn("fills-history?instType=SPOT&limit=100", requested_url)


if __name__ == "__main__":
    unittest.main()
