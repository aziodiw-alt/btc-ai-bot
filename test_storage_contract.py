import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

import database

WEB_DIR = Path(__file__).resolve().parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import dashboard_history
import dashboard_trades


def table_columns(database_path, table_name):
    with sqlite3.connect(database_path) as connection:
        return [
            row[1]
            for row in connection.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
        ]


class StorageSchemaContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        temp_path = Path(self.temp_directory.name)
        self.telegram_database = temp_path / "trades.db"
        self.dashboard_database = temp_path / "dashboard.db"

        self.original_database_path = database.DB_PATH
        self.original_telegram_path = dashboard_trades.TELEGRAM_DATABASE_PATH
        self.original_dashboard_path = dashboard_history.DATABASE_PATH

        database.DB_PATH = self.telegram_database
        dashboard_trades.TELEGRAM_DATABASE_PATH = self.telegram_database
        dashboard_history.DATABASE_PATH = str(self.dashboard_database)

    def tearDown(self):
        database.DB_PATH = self.original_database_path
        dashboard_trades.TELEGRAM_DATABASE_PATH = self.original_telegram_path
        dashboard_history.DATABASE_PATH = self.original_dashboard_path
        self.temp_directory.cleanup()

    def test_telegram_database_schema_is_stable(self):
        database.init_database()

        self.assertEqual(
            table_columns(self.telegram_database, "trades"),
            [
                "id",
                "telegram_user_id",
                "symbol",
                "entry_price",
                "quote_amount",
                "btc_quantity",
                "fee_rate",
                "opened_at",
                "exit_price",
                "closed_at",
                "gross_pnl",
                "net_pnl",
                "net_pnl_pct",
                "status",
            ],
        )
        self.assertEqual(
            table_columns(self.telegram_database, "bybit_executions"),
            [
                "id",
                "telegram_user_id",
                "transaction_id",
                "symbol",
                "side",
                "order_type",
                "fee_coin",
                "fee_amount",
                "filled_value",
                "filled_price",
                "filled_quantity",
                "order_id",
                "executed_at",
            ],
        )
        self.assertEqual(
            table_columns(self.telegram_database, "signal_subscribers"),
            [
                "telegram_chat_id",
                "enabled",
                "last_signal_key",
                "updated_at",
            ],
        )

    def test_dashboard_trade_access_adds_compatible_columns(self):
        database.init_database()

        connection = dashboard_trades._connect()
        connection.close()

        self.assertEqual(
            table_columns(self.telegram_database, "pending_orders"),
            [
                "id",
                "telegram_user_id",
                "order_id",
                "symbol",
                "side",
                "order_type",
                "order_value",
                "order_price",
                "order_quantity",
                "created_at",
                "status",
                "updated_at",
                "strategy_key",
                "strategy_confidence",
                "strategy_reason",
            ],
        )
        self.assertEqual(
            table_columns(self.telegram_database, "bybit_executions")[-2:],
            ["strategy_key", "strategy_confidence"],
        )

    def test_dashboard_history_schema_and_snapshot_throttle_are_stable(self):
        result = {
            "display_symbol": "BTC/USDT",
            "strategy_key": "swing",
            "price": 100.0,
            "total_score": 75,
            "grade": "A",
            "decision": "FIXTURE",
            "trend_score": 30,
            "entry_score": 15,
            "indicators_score": 10,
            "sentiment_score": 20,
            "rsi_4h": 50.0,
            "reasons": ["reason"],
            "warnings": ["warning"],
        }

        first = dashboard_history.save_snapshot_if_due(result)
        second = dashboard_history.save_snapshot_if_due(result)

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            table_columns(self.dashboard_database, "analysis_history"),
            [
                "id",
                "created_at",
                "created_at_unix",
                "symbol",
                "price",
                "total_score",
                "grade",
                "decision",
                "signal_type",
                "trend_score",
                "entry_score",
                "indicators_score",
                "sentiment_score",
                "rsi_4h",
                "reasons_json",
                "warnings_json",
                "strategy_name",
            ],
        )
        with sqlite3.connect(self.dashboard_database) as connection:
            stored = connection.execute(
                "SELECT symbol, strategy_name, signal_type, reasons_json "
                "FROM analysis_history"
            ).fetchone()
        self.assertEqual(stored, ("BTC/USDT", "swing", "BUY", '["reason"]'))
        self.assertEqual(
            [
                item["key"]
                for item in dashboard_history.get_strategy_comparison(
                    "BTC/USDT"
                )
            ],
            ["swing", "fast", "alpha"],
        )

    def test_legacy_history_schema_is_upgraded_without_losing_rows(self):
        with sqlite3.connect(self.dashboard_database) as connection:
            connection.execute(
                """
                CREATE TABLE analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    created_at_unix INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    total_score INTEGER NOT NULL,
                    grade TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    trend_score INTEGER NOT NULL,
                    entry_score INTEGER NOT NULL,
                    indicators_score INTEGER NOT NULL,
                    sentiment_score INTEGER NOT NULL,
                    rsi_4h REAL,
                    reasons_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO analysis_history (
                    created_at, created_at_unix, symbol, price,
                    total_score, grade, decision, signal_type,
                    trend_score, entry_score, indicators_score,
                    sentiment_score, rsi_4h, reasons_json, warnings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "01.01.2026 12:00",
                    1_767_268_800,
                    "BTC/USDT",
                    100.0,
                    65,
                    "B",
                    "LEGACY",
                    "WAIT",
                    20,
                    15,
                    10,
                    20,
                    50.0,
                    "[]",
                    "[]",
                ),
            )

        connection = dashboard_history._connect()
        connection.close()

        self.assertIn(
            "strategy_name",
            table_columns(self.dashboard_database, "analysis_history"),
        )
        with sqlite3.connect(self.dashboard_database) as connection:
            stored = connection.execute(
                "SELECT decision, strategy_name FROM analysis_history"
            ).fetchone()
        self.assertEqual(stored, ("LEGACY", "swing"))

    def test_legacy_trade_tables_are_upgraded_without_losing_rows(self):
        with sqlite3.connect(self.telegram_database) as connection:
            connection.execute(
                """
                CREATE TABLE pending_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    order_id TEXT,
                    symbol TEXT NOT NULL DEFAULT 'BTCUSDT',
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL DEFAULT 'LIMIT',
                    order_value REAL NOT NULL,
                    order_price REAL NOT NULL,
                    order_quantity REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    updated_at TEXT NOT NULL,
                    UNIQUE(telegram_user_id, order_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE bybit_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    transaction_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT,
                    fee_coin TEXT,
                    fee_amount REAL NOT NULL DEFAULT 0,
                    filled_value REAL NOT NULL,
                    filled_price REAL NOT NULL,
                    filled_quantity REAL NOT NULL,
                    order_id TEXT,
                    executed_at TEXT NOT NULL,
                    UNIQUE(telegram_user_id, transaction_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO pending_orders (
                    telegram_user_id, order_id, symbol, side,
                    order_value, order_price, order_quantity,
                    created_at, updated_at
                )
                VALUES (1, 'legacy-order', 'BTCUSDT', 'BUY',
                        100, 10000, 0.01, 'legacy-date', 'legacy-date')
                """
            )
            connection.execute(
                """
                INSERT INTO bybit_executions (
                    telegram_user_id, transaction_id, symbol, side,
                    fee_amount, filled_value, filled_price,
                    filled_quantity, executed_at
                )
                VALUES (1, 'legacy-execution', 'BTCUSDT', 'BUY',
                        0.1, 100, 10000, 0.01, 'legacy-date')
                """
            )

        connection = dashboard_trades._connect()
        connection.close()

        self.assertEqual(
            table_columns(self.telegram_database, "pending_orders")[-3:],
            ["strategy_key", "strategy_confidence", "strategy_reason"],
        )
        self.assertEqual(
            table_columns(self.telegram_database, "bybit_executions")[-2:],
            ["strategy_key", "strategy_confidence"],
        )
        with sqlite3.connect(self.telegram_database) as connection:
            order = connection.execute(
                "SELECT order_id, strategy_key FROM pending_orders"
            ).fetchone()
            execution = connection.execute(
                "SELECT transaction_id, strategy_key FROM bybit_executions"
            ).fetchone()
        self.assertEqual(order, ("legacy-order", None))
        self.assertEqual(execution, ("legacy-execution", None))


if __name__ == "__main__":
    unittest.main()
