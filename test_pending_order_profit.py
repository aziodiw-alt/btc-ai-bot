import unittest
from unittest.mock import patch

from web.dashboard_trades import get_pending_orders


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        return _Rows(self.rows)


class PendingOrderProfitTests(unittest.TestCase):
    def test_sell_orders_share_available_fifo_quantity(self):
        rows = [
            {
                "id": 1,
                "side": "SELL",
                "order_price": 11000,
                "order_quantity": 0.01,
                "order_value": 110,
            },
            {
                "id": 2,
                "side": "SELL",
                "order_price": 11000,
                "order_quantity": 0.01,
                "order_value": 110,
            },
        ]
        fifo = {
            "open_quantity": 0.015,
            "open_cost": 150,
        }

        with (
            patch(
                "web.dashboard_trades._connect",
                return_value=_Connection(rows),
            ),
            patch(
                "web.dashboard_trades._resolve_user_id",
                return_value=1,
            ),
            patch(
                "web.dashboard_trades._get_bybit_fifo_statistics",
                return_value=fifo,
            ),
        ):
            orders = get_pending_orders(symbol="BTCUSDT")

        self.assertAlmostEqual(orders[0]["matched_quantity"], 0.01)
        self.assertAlmostEqual(orders[1]["matched_quantity"], 0.005)
        self.assertTrue(orders[0]["profit_is_complete"])
        self.assertFalse(orders[1]["profit_is_complete"])
        self.assertAlmostEqual(orders[1]["profit_coverage_pct"], 50)
        # FIFO cost already includes the entry fee, so only the future
        # sell fee is deducted: 110 - 100 - 0.11.
        self.assertAlmostEqual(
            orders[0]["estimated_profit_usdt"],
            9.89,
        )


if __name__ == "__main__":
    unittest.main()
