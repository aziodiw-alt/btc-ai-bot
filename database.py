import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        str(Path(__file__).with_name("trades.db")),
    )
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DEFAULT_FEE_RATE = 0.001  # 0.1% за операцию; приблизительное значение.


def _connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL DEFAULT 'BTCUSDT',
                entry_price REAL NOT NULL,
                quote_amount REAL NOT NULL,
                btc_quantity REAL NOT NULL,
                fee_rate REAL NOT NULL,
                opened_at TEXT NOT NULL,
                exit_price REAL,
                closed_at TEXT,
                gross_pnl REAL,
                net_pnl REAL,
                net_pnl_pct REAL,
                status TEXT NOT NULL DEFAULT 'OPEN'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bybit_executions (
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
            CREATE TABLE IF NOT EXISTS signal_subscribers (
                telegram_chat_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_signal_key TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )


def get_open_trade(telegram_user_id):
    with _connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM trades
            WHERE telegram_user_id = ? AND status = 'OPEN'
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_user_id,),
        ).fetchone()


def open_trade(
    telegram_user_id,
    entry_price,
    quote_amount,
    fee_rate=DEFAULT_FEE_RATE,
):
    if get_open_trade(telegram_user_id):
        raise ValueError("Сначала закрой уже открытую сделку.")

    btc_quantity = quote_amount / entry_price
    opened_at = datetime.now(timezone.utc).isoformat()

    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO trades (
                telegram_user_id,
                entry_price,
                quote_amount,
                btc_quantity,
                fee_rate,
                opened_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                entry_price,
                quote_amount,
                btc_quantity,
                fee_rate,
                opened_at,
            ),
        )

    return cursor.lastrowid


def close_trade(telegram_user_id, exit_price):
    trade = get_open_trade(telegram_user_id)

    if not trade:
        raise ValueError("Открытая сделка не найдена.")

    entry_value = float(trade["quote_amount"])
    exit_value = float(trade["btc_quantity"]) * exit_price
    entry_fee = entry_value * float(trade["fee_rate"])
    exit_fee = exit_value * float(trade["fee_rate"])

    gross_pnl = exit_value - entry_value
    net_pnl = gross_pnl - entry_fee - exit_fee
    net_pnl_pct = net_pnl / entry_value * 100
    closed_at = datetime.now(timezone.utc).isoformat()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE trades
            SET exit_price = ?,
                closed_at = ?,
                gross_pnl = ?,
                net_pnl = ?,
                net_pnl_pct = ?,
                status = 'CLOSED'
            WHERE id = ?
            """,
            (
                exit_price,
                closed_at,
                gross_pnl,
                net_pnl,
                net_pnl_pct,
                trade["id"],
            ),
        )

    return {
        "id": trade["id"],
        "entry_price": float(trade["entry_price"]),
        "exit_price": exit_price,
        "quote_amount": entry_value,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "net_pnl_pct": net_pnl_pct,
        "fees": entry_fee + exit_fee,
    }


def get_statistics(telegram_user_id):
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END) AS losses,
                COALESCE(SUM(net_pnl), 0) AS total_net_pnl,
                COALESCE(AVG(net_pnl_pct), 0) AS avg_net_pnl_pct
            FROM trades
            WHERE telegram_user_id = ? AND status = 'CLOSED'
            """,
            (telegram_user_id,),
        ).fetchone()

    total = int(row["total"] or 0)
    wins = int(row["wins"] or 0)

    return {
        "total": total,
        "wins": wins,
        "losses": int(row["losses"] or 0),
        "win_rate": wins / total * 100 if total else 0.0,
        "total_net_pnl": float(row["total_net_pnl"] or 0),
        "avg_net_pnl_pct": float(row["avg_net_pnl_pct"] or 0),
    }


def insert_bybit_execution(telegram_user_id, execution):
    """Добавляет одно исполнение Bybit. Возвращает True, если строка новая."""
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO bybit_executions (
                    telegram_user_id,
                    transaction_id,
                    symbol,
                    side,
                    order_type,
                    fee_coin,
                    fee_amount,
                    filled_value,
                    filled_price,
                    filled_quantity,
                    order_id,
                    executed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    execution["transaction_id"],
                    execution["symbol"],
                    execution["side"],
                    execution["order_type"],
                    execution["fee_coin"],
                    execution["fee_amount"],
                    execution["filled_value"],
                    execution["filled_price"],
                    execution["filled_quantity"],
                    execution["order_id"],
                    execution["executed_at"],
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_bybit_executions(telegram_user_id, symbol="BTCUSDT"):
    with _connect() as connection:
        return connection.execute(
            """
            SELECT *
            FROM bybit_executions
            WHERE telegram_user_id = ? AND symbol = ?
            ORDER BY executed_at ASC, id ASC
            """,
            (telegram_user_id, symbol),
        ).fetchall()


def clear_bybit_executions(telegram_user_id):
    """Удаляет только импортированные исполнения пользователя."""
    with _connect() as connection:
        cursor = connection.execute(
            """
            DELETE FROM bybit_executions
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        )
    return cursor.rowcount


def get_bybit_fifo_statistics(telegram_user_id, symbol="BTCUSDT"):
    """
    Сопоставляет покупки и продажи методом FIFO.

    Комиссия покупки в BTC уменьшает полученное количество.
    Комиссия продажи в USDT уменьшает выручку.
    """
    rows = get_bybit_executions(telegram_user_id, symbol)
    lots = []
    closed_results = []
    unmatched_sell_qty = 0.0

    for row in rows:
        quantity = float(row["filled_quantity"])
        value = float(row["filled_value"])
        fee = float(row["fee_amount"])
        fee_coin = (row["fee_coin"] or "").upper()
        side = row["side"].upper()

        if side == "BUY":
            net_quantity = quantity - fee if fee_coin == "BTC" else quantity
            quote_cost = value + fee if fee_coin in {"USDT", "USDC"} else value

            if net_quantity > 0:
                lots.append(
                    {
                        "quantity": net_quantity,
                        "unit_cost": quote_cost / net_quantity,
                    }
                )
            continue

        if side != "SELL" or quantity <= 0:
            continue

        quote_proceeds = value - fee if fee_coin in {"USDT", "USDC"} else value
        unit_proceeds = quote_proceeds / quantity
        remaining = quantity
        matched_cost = 0.0
        matched_proceeds = 0.0
        matched_quantity = 0.0

        while remaining > 1e-12 and lots:
            lot = lots[0]
            matched = min(remaining, lot["quantity"])

            matched_cost += matched * lot["unit_cost"]
            matched_proceeds += matched * unit_proceeds
            matched_quantity += matched

            lot["quantity"] -= matched
            remaining -= matched

            if lot["quantity"] <= 1e-12:
                lots.pop(0)

        unmatched_sell_qty += max(remaining, 0.0)

        if matched_quantity > 0:
            pnl = matched_proceeds - matched_cost
            pnl_pct = pnl / matched_cost * 100 if matched_cost else 0.0
            closed_results.append(
                {
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "matched_quantity": matched_quantity,
                }
            )

    open_quantity = sum(lot["quantity"] for lot in lots)
    open_cost = sum(lot["quantity"] * lot["unit_cost"] for lot in lots)
    total_closed = len(closed_results)
    wins = sum(1 for item in closed_results if item["pnl"] > 0)
    total_pnl = sum(item["pnl"] for item in closed_results)
    average_pnl_pct = (
        sum(item["pnl_pct"] for item in closed_results) / total_closed
        if total_closed
        else 0.0
    )

    return {
        "execution_count": len(rows),
        "closed_trades": total_closed,
        "wins": wins,
        "losses": total_closed - wins,
        "win_rate": wins / total_closed * 100 if total_closed else 0.0,
        "total_net_pnl": total_pnl,
        "average_pnl_pct": average_pnl_pct,
        "open_quantity": open_quantity,
        "open_average_price": open_cost / open_quantity if open_quantity else 0.0,
        "unmatched_sell_quantity": unmatched_sell_qty,
    }


def toggle_signal_subscription(telegram_chat_id):
    """Включает или выключает автоматические сигналы для Telegram-чата."""
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT enabled
            FROM signal_subscribers
            WHERE telegram_chat_id = ?
            """,
            (telegram_chat_id,),
        ).fetchone()

        enabled = 0 if row and row["enabled"] else 1

        connection.execute(
            """
            INSERT INTO signal_subscribers (
                telegram_chat_id,
                enabled,
                last_signal_key,
                updated_at
            )
            VALUES (?, ?, NULL, ?)
            ON CONFLICT(telegram_chat_id) DO UPDATE SET
                enabled = excluded.enabled,
                last_signal_key = NULL,
                updated_at = excluded.updated_at
            """,
            (telegram_chat_id, enabled, now),
        )

    return bool(enabled)


def get_signal_subscribers():
    """Возвращает чаты, в которых автоматические сигналы включены."""
    with _connect() as connection:
        return connection.execute(
            """
            SELECT telegram_chat_id, last_signal_key
            FROM signal_subscribers
            WHERE enabled = 1
            ORDER BY telegram_chat_id
            """
        ).fetchall()


def set_last_signal_key(
    telegram_chat_id,
    signal_key,
    symbol="BTCUSDT",
):
    """Stores independent anti-duplicate keys for every market symbol."""
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT last_signal_key
            FROM signal_subscribers
            WHERE telegram_chat_id = ?
            """,
            (telegram_chat_id,),
        ).fetchone()

        state = {}
        raw_state = row["last_signal_key"] if row else None

        if raw_state:
            try:
                parsed = json.loads(raw_state)
                if isinstance(parsed, dict):
                    state = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                state = {}

        normalized_symbol = str(symbol).replace("/", "").upper()

        if signal_key is None:
            state.pop(normalized_symbol, None)
        else:
            state[normalized_symbol] = str(signal_key)

        serialized_state = (
            json.dumps(state, ensure_ascii=False, sort_keys=True)
            if state
            else None
        )

        connection.execute(
            """
            UPDATE signal_subscribers
            SET last_signal_key = ?, updated_at = ?
            WHERE telegram_chat_id = ?
            """,
            (serialized_state, now, telegram_chat_id),
        )
