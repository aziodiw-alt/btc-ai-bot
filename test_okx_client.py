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


if __name__ == "__main__":
    unittest.main()
