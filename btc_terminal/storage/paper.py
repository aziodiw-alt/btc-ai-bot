"""Persistent Binance paper-trading simulator.

This module never calls an exchange client. It only evaluates virtual orders
against a market price supplied by the caller.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATABASE_PATH = os.getenv("DASHBOARD_DATABASE_PATH", os.path.join(DATA_DIR, "dashboard.db"))


def _now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS paper_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT NOT NULL DEFAULT 'binance', symbol TEXT NOT NULL,
            strategy_name TEXT NOT NULL DEFAULT 'alpha', status TEXT NOT NULL,
            initial_balance REAL NOT NULL, cash_balance REAL NOT NULL,
            asset_balance REAL NOT NULL DEFAULT 0, invested_cost REAL NOT NULL DEFAULT 0,
            average_entry REAL, fee_rate REAL NOT NULL,
            stop_loss REAL NOT NULL, take_profit_1 REAL NOT NULL, take_profit_2 REAL NOT NULL,
            tp1_done INTEGER NOT NULL DEFAULT 0, realized_pnl REAL NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS paper_one_active_symbol_idx
        ON paper_sessions(exchange, symbol) WHERE status = 'ACTIVE';
        CREATE TABLE IF NOT EXISTS paper_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
            label TEXT NOT NULL, side TEXT NOT NULL, allocation_pct REAL,
            limit_price REAL NOT NULL, quantity REAL NOT NULL, value REAL NOT NULL,
            fee REAL NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, filled_at TEXT,
            FOREIGN KEY(session_id) REFERENCES paper_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS paper_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
            event_type TEXT NOT NULL, price REAL, quantity REAL, quote_value REAL,
            fee REAL NOT NULL DEFAULT 0, pnl REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES paper_sessions(id)
        );
        """
    )
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def start_paper_session(symbol, budget, alpha_result, fee_rate=0.001):
    symbol = str(symbol).upper()
    budget = float(budget)
    fee_rate = float(fee_rate)
    if budget <= 0:
        raise ValueError("Виртуальный депозит должен быть больше 0 USDT.")
    entries = alpha_result.get("entry_plan") or []
    if len(entries) != 3:
        raise ValueError("Alpha должна предоставить три уровня входа.")
    now = _now()
    with _connect() as connection:
        if connection.execute(
            "SELECT 1 FROM paper_sessions WHERE exchange='binance' AND symbol=? AND status='ACTIVE'",
            (symbol,),
        ).fetchone():
            raise ValueError("Для этого актива уже запущена виртуальная сессия.")
        cursor = connection.execute(
            """INSERT INTO paper_sessions(
                symbol,status,initial_balance,cash_balance,fee_rate,stop_loss,
                take_profit_1,take_profit_2,started_at,updated_at
            ) VALUES (?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, budget, budget, fee_rate, float(alpha_result["stop_loss"]),
             float(alpha_result["take_profit_1"]), float(alpha_result["take_profit_2"]), now, now),
        )
        session_id = cursor.lastrowid
        for index, entry in enumerate(entries, 1):
            pct = float(entry.get("allocation", entry.get("allocation_pct", 0)))
            price = float(entry["price"])
            allocation = budget * pct / 100
            quantity = allocation / (price * (1 + fee_rate))
            value = price * quantity
            fee = value * fee_rate
            connection.execute(
                """INSERT INTO paper_orders(
                    session_id,label,side,allocation_pct,limit_price,quantity,value,fee,status,created_at
                ) VALUES (?, ?, 'BUY', ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (session_id, entry.get("label", f"Entry {index}"), pct, price, quantity, value, fee, now),
            )
        connection.execute(
            "INSERT INTO paper_events(session_id,event_type,quote_value,created_at) VALUES (?, 'START', ?, ?)",
            (session_id, budget, now),
        )
    return session_id


def _sell(connection, session, price, quantity, event_type, final=False):
    quantity = min(float(quantity), float(session["asset_balance"]))
    if quantity <= 0:
        return
    asset_before = float(session["asset_balance"])
    cost = float(session["invested_cost"]) * quantity / asset_before
    gross = quantity * price
    fee = gross * float(session["fee_rate"])
    net = gross - fee
    pnl = net - cost
    remaining_asset = asset_before - quantity
    remaining_cost = max(0.0, float(session["invested_cost"]) - cost)
    status = "COMPLETED" if final else "ACTIVE"
    now = _now()
    connection.execute(
        """UPDATE paper_sessions SET cash_balance=cash_balance+?, asset_balance=?,
        invested_cost=?, realized_pnl=realized_pnl+?, status=?, updated_at=?,
        ended_at=CASE WHEN ? THEN ? ELSE ended_at END WHERE id=?""",
        (net, remaining_asset, remaining_cost, pnl, status, now, int(final), now, session["id"]),
    )
    connection.execute(
        """INSERT INTO paper_events(session_id,event_type,price,quantity,quote_value,fee,pnl,created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session["id"], event_type, price, quantity, gross, fee, pnl, now),
    )


def evaluate_paper_symbol(symbol, current_price):
    symbol, current_price = str(symbol).upper(), float(current_price)
    with _connect() as connection:
        session = connection.execute(
            "SELECT * FROM paper_sessions WHERE exchange='binance' AND symbol=? AND status='ACTIVE'",
            (symbol,),
        ).fetchone()
        if not session:
            return None
        orders = connection.execute(
            "SELECT * FROM paper_orders WHERE session_id=? AND status='PENDING' ORDER BY limit_price DESC",
            (session["id"],),
        ).fetchall()
        for order in orders:
            if current_price <= float(order["limit_price"]):
                cost = float(order["value"]) + float(order["fee"])
                session = connection.execute("SELECT * FROM paper_sessions WHERE id=?", (session["id"],)).fetchone()
                if cost <= float(session["cash_balance"]) + 1e-8:
                    old_asset = float(session["asset_balance"])
                    new_asset = old_asset + float(order["quantity"])
                    new_cost = float(session["invested_cost"]) + cost
                    now = _now()
                    connection.execute(
                        """UPDATE paper_sessions SET cash_balance=cash_balance-?, asset_balance=?,
                        invested_cost=?, average_entry=?, updated_at=? WHERE id=?""",
                        (cost, new_asset, new_cost, new_cost / new_asset, now, session["id"]),
                    )
                    connection.execute("UPDATE paper_orders SET status='FILLED', filled_at=? WHERE id=?", (now, order["id"]))
                    connection.execute(
                        """INSERT INTO paper_events(session_id,event_type,price,quantity,quote_value,fee,created_at)
                        VALUES (?, 'FILL_BUY', ?, ?, ?, ?, ?)""",
                        (session["id"], order["limit_price"], order["quantity"], order["value"], order["fee"], now),
                    )
        session = connection.execute("SELECT * FROM paper_sessions WHERE id=?", (session["id"],)).fetchone()
        if float(session["asset_balance"]) > 0:
            if current_price <= float(session["stop_loss"]):
                connection.execute("UPDATE paper_orders SET status='CANCELLED' WHERE session_id=? AND status='PENDING'", (session["id"],))
                _sell(connection, session, current_price, session["asset_balance"], "STOP_LOSS", final=True)
            elif current_price >= float(session["take_profit_2"]):
                connection.execute("UPDATE paper_orders SET status='CANCELLED' WHERE session_id=? AND status='PENDING'", (session["id"],))
                _sell(connection, session, current_price, session["asset_balance"], "TAKE_PROFIT_2", final=True)
            elif current_price >= float(session["take_profit_1"]) and not session["tp1_done"]:
                connection.execute("UPDATE paper_orders SET status='CANCELLED' WHERE session_id=? AND status='PENDING'", (session["id"],))
                _sell(connection, session, current_price, float(session["asset_balance"]) / 2, "TAKE_PROFIT_1")
                connection.execute("UPDATE paper_sessions SET tp1_done=1 WHERE id=?", (session["id"],))
    return get_paper_dashboard(symbol, current_price)


def stop_paper_session(session_id, current_price):
    with _connect() as connection:
        session = connection.execute("SELECT * FROM paper_sessions WHERE id=? AND status='ACTIVE'", (int(session_id),)).fetchone()
        if not session:
            raise ValueError("Активная виртуальная сессия не найдена.")
        connection.execute("UPDATE paper_orders SET status='CANCELLED' WHERE session_id=? AND status='PENDING'", (session["id"],))
        if float(session["asset_balance"]) > 0:
            _sell(connection, session, float(current_price), session["asset_balance"], "EMERGENCY_STOP", final=True)
            connection.execute("UPDATE paper_sessions SET status='STOPPED' WHERE id=?", (session["id"],))
        else:
            now = _now()
            connection.execute("UPDATE paper_sessions SET status='STOPPED',updated_at=?,ended_at=? WHERE id=?", (now, now, session["id"]))
            connection.execute("INSERT INTO paper_events(session_id,event_type,price,created_at) VALUES (?, 'EMERGENCY_STOP', ?, ?)", (session["id"], float(current_price), now))


def get_active_paper_symbols():
    with _connect() as connection:
        return [row["symbol"] for row in connection.execute("SELECT symbol FROM paper_sessions WHERE status='ACTIVE'").fetchall()]


def get_paper_dashboard(symbol, current_price=None):
    symbol = str(symbol).upper()
    with _connect() as connection:
        active = connection.execute("SELECT * FROM paper_sessions WHERE symbol=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1", (symbol,)).fetchone()
        sessions = connection.execute("SELECT * FROM paper_sessions WHERE symbol=? ORDER BY id DESC LIMIT 10", (symbol,)).fetchall()
        orders, events = [], []
        if active:
            orders = connection.execute("SELECT * FROM paper_orders WHERE session_id=? ORDER BY id", (active["id"],)).fetchall()
            events = connection.execute("SELECT * FROM paper_events WHERE session_id=? ORDER BY id DESC LIMIT 20", (active["id"],)).fetchall()
        completed = [dict(row) for row in sessions if row["status"] != "ACTIVE"]
        total_pnl = sum(float(row["realized_pnl"]) for row in completed)
        data = dict(active) if active else None
        if data:
            price = float(current_price or data["average_entry"] or 0)
            data["equity"] = float(data["cash_balance"]) + float(data["asset_balance"]) * price
            data["total_pnl"] = data["equity"] - float(data["initial_balance"])
        return {
            "active": data, "orders": [dict(row) for row in orders], "events": [dict(row) for row in events],
            "history": completed, "stats": {"completed": len(completed), "wins": sum(row["realized_pnl"] > 0 for row in completed), "total_pnl": total_pnl},
        }
