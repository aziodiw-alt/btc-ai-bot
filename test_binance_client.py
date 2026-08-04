import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

from binance_client import BinanceReadOnlyClient


class BinanceReadOnlyClientTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.client = BinanceReadOnlyClient(
            api_key="key",
            api_secret="secret",
            base_url="https://api.binance.com",
            session=self.session,
            clock=lambda: 1700000000,
        )

    @staticmethod
    def _response(payload):
        response = Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    def test_signed_account_request_and_permissions(self):
        self.session.get.side_effect = [
            self._response({
                "canTrade": False,
                "canWithdraw": False,
                "accountType": "SPOT",
                "balances": [
                    {"asset": "USDT", "free": "25", "locked": "5"},
                    {"asset": "BTC", "free": "0", "locked": "0"},
                ],
            }),
            self._response([{"symbol": "BTCUSDT", "price": "60000"}]),
        ]

        status = self.client.connection_status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["client_mode"], "read_only")
        self.assertFalse(status["account_can_trade"])
        self.assertFalse(status["account_can_withdraw"])
        self.assertNotIn("can_trade", status)
        self.assertNotIn("can_withdraw", status)
        self.assertEqual(status["currencies"][0]["total"], 30.0)
        params = self.session.get.call_args_list[0].kwargs["params"]
        self.assertEqual(params["timestamp"], 1700000000000)
        self.assertEqual(len(params["signature"]), 64)

    def test_open_orders_are_normalized(self):
        self.session.get.return_value = self._response(
            [{
                "orderId": 123,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "price": "62000",
                "origQty": "0.01",
                "executedQty": "0.002",
                "status": "PARTIALLY_FILLED",
                "time": 1700000000000,
            }]
        )

        orders = self.client.get_open_orders("BTCUSDT")

        self.assertAlmostEqual(orders[0]["remaining_quantity"], 0.008)
        self.assertAlmostEqual(orders[0]["remaining_value"], 496.0)

    def test_client_exposes_no_order_or_withdrawal_methods(self):
        forbidden = ("create_order", "place_order", "cancel_order", "withdraw")
        for method_name in forbidden:
            self.assertFalse(hasattr(self.client, method_name))

    def test_api_error_does_not_include_credentials(self):
        self.session.get.return_value = self._response(
            {"code": -2015, "msg": "Invalid API-key"}
        )
        with self.assertRaisesRegex(RuntimeError, "Invalid API-key"):
            self.client.get_account()


if __name__ == "__main__":
    unittest.main()
