"""Persistent, exchange-isolated paper scalping for Binance Spot."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATABASE_PATH = os.getenv("DASHBOARD_DATABASE_PATH", os.path.join(DATA_DIR, "dashboard.db"))
PROFILES = {
    "scalp_5m": {
        "label": "Scalp 5m",
        "interval": "5m",
        "allocation": 0.70,
        "stop_pct": 0.0040,
        "target_pct": 0.0070,
        "ema_fast": 9,
        "ema_slow": 21,
        "rsi_low": 52,
        "rsi_high": 68,
        "volume_ratio": 1.05,
        "momentum_bars": 3,
        "momentum_min": 0.0008,
        "max_losses": 3,
    },
    "scalp_aggressive_1m": {
        "label": "Scalp Aggressive 1m",
        "interval": "1m",
        "allocation": 1.00,
        "stop_pct": 0.0030,
        "target_pct": 0.0050,
        "ema_fast": 5,
        "ema_slow": 13,
        "rsi_low": 48,
        "rsi_high": 75,
        "volume_ratio": 0.85,
        "momentum_bars": 2,
        "momentum_min": 0.0003,
        "max_losses": 4,
    },
}


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
        CREATE TABLE IF NOT EXISTS scalp_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL,
            profile TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',
            initial_balance REAL NOT NULL, cash_balance REAL NOT NULL,
            quantity REAL NOT NULL DEFAULT 0, entry_price REAL,
            entry_cost REAL NOT NULL DEFAULT 0, stop_price REAL, target_price REAL,
            fee_rate REAL NOT NULL DEFAULT 0.001, realized_pnl REAL NOT NULL DEFAULT 0,
            consecutive_losses INTEGER NOT NULL DEFAULT 0, last_candle_time TEXT,
            started_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS scalp_one_active_profile_idx
        ON scalp_accounts(symbol, profile) WHERE status='ACTIVE';
        CREATE TABLE IF NOT EXISTS scalp_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
            opened_at TEXT NOT NULL, closed_at TEXT, entry_price REAL NOT NULL,
            exit_price REAL, quantity REAL NOT NULL, buy_fee REAL NOT NULL,
            sell_fee REAL, pnl REAL, exit_reason TEXT, signal_note TEXT,
            FOREIGN KEY(account_id) REFERENCES scalp_accounts(id)
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


def start_scalp_account(symbol, profile, budget, fee_rate=0.001):
    symbol, profile, budget = str(symbol).upper(), str(profile), float(budget)
    if profile not in PROFILES:
        raise ValueError("Неизвестный профиль скальпинга.")
    if budget <= 0:
        raise ValueError("Виртуальный депозит должен быть больше 0 USDT.")
    now = _now()
    with _connect() as connection:
        if connection.execute(
            "SELECT 1 FROM scalp_accounts WHERE symbol=? AND profile=? AND status='ACTIVE'",
            (symbol, profile),
        ).fetchone():
            raise ValueError("Этот профиль уже запущен для выбранного актива.")
        cursor = connection.execute(
            """INSERT INTO scalp_accounts(
            symbol,profile,initial_balance,cash_balance,fee_rate,started_at,updated_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (symbol, profile, budget, budget, float(fee_rate), now, now),
        )
        return cursor.lastrowid


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    result = 100 - (100 / (1 + gain / loss.replace(0, float("nan"))))
    result = result.where(loss != 0, 100)
    return result.where((gain != 0) | (loss != 0), 50)


def calculate_scalp_signal(candles, profile):
    config = PROFILES[profile]
    frame = candles.copy()
    if len(frame) < max(30, config["ema_slow"] + 5):
        return {"buy": False, "reason": "Недостаточно свечей"}
    close = pd.to_numeric(frame["close"])
    volume = pd.to_numeric(frame["volume"])
    fast = close.ewm(span=config["ema_fast"], adjust=False).mean().iloc[-1]
    slow = close.ewm(span=config["ema_slow"], adjust=False).mean().iloc[-1]
    rsi = float(_rsi(close).iloc[-1])
    volume_ratio = float(volume.iloc[-1] / volume.rolling(20).mean().iloc[-1])
    momentum = float(close.iloc[-1] / close.iloc[-1 - config["momentum_bars"]] - 1)
    buy = (
        fast > slow
        and close.iloc[-1] > fast
        and config["rsi_low"] <= rsi <= config["rsi_high"]
        and volume_ratio >= config["volume_ratio"]
        and momentum >= config["momentum_min"]
    )
    return {
        "buy": bool(buy),
        "rsi": round(rsi, 1),
        "volume_ratio": round(volume_ratio, 2),
        "momentum_pct": round(momentum * 100, 3),
        "reason": f"RSI {rsi:.1f} · объём {volume_ratio:.2f}x · импульс {momentum*100:.3f}%",
    }


def _close_position(connection, account, price, reason):
    gross = float(account["quantity"]) * price
    fee = gross * float(account["fee_rate"])
    net = gross - fee
    pnl = net - float(account["entry_cost"])
    losses = int(account["consecutive_losses"]) + 1 if pnl < 0 else 0
    now = _now()
    connection.execute(
        """UPDATE scalp_accounts SET cash_balance=cash_balance+?, quantity=0,
        entry_price=NULL,entry_cost=0,stop_price=NULL,target_price=NULL,
        realized_pnl=realized_pnl+?,consecutive_losses=?,updated_at=? WHERE id=?""",
        (net, pnl, losses, now, account["id"]),
    )
    connection.execute(
        """UPDATE scalp_trades SET closed_at=?,exit_price=?,sell_fee=?,pnl=?,exit_reason=?
        WHERE id=(SELECT id FROM scalp_trades WHERE account_id=? AND closed_at IS NULL ORDER BY id DESC LIMIT 1)""",
        (now, price, fee, pnl, reason, account["id"]),
    )


def evaluate_scalp_account(account_id, candles, current_price=None):
    # Binance includes the currently forming candle. Signals must use only a
    # completed candle so the decision cannot repaint during the interval.
    closed_candles = candles.iloc[:-1].copy() if len(candles) > 1 else candles.copy()
    with _connect() as connection:
        account = connection.execute(
            "SELECT * FROM scalp_accounts WHERE id=? AND status='ACTIVE'", (int(account_id),)
        ).fetchone()
        if not account:
            return None
        config = PROFILES[account["profile"]]
        price = float(current_price or candles["close"].iloc[-1])
        if float(account["quantity"]) > 0:
            if price <= float(account["stop_price"]):
                _close_position(connection, account, price, "STOP")
            elif price >= float(account["target_price"]):
                _close_position(connection, account, price, "TARGET")
            connection.commit()
            return get_scalp_dashboard(account["symbol"], price)
        candle_time = str(closed_candles["time"].iloc[-1])
        if account["last_candle_time"] == candle_time:
            return get_scalp_dashboard(account["symbol"], price)
        connection.execute(
            "UPDATE scalp_accounts SET last_candle_time=?,updated_at=? WHERE id=?",
            (candle_time, _now(), account["id"]),
        )
        if int(account["consecutive_losses"]) >= config["max_losses"]:
            connection.commit()
            return get_scalp_dashboard(account["symbol"], price)
        signal = calculate_scalp_signal(closed_candles, account["profile"])
        if signal["buy"]:
            available = float(account["cash_balance"]) * config["allocation"]
            quantity = available / (price * (1 + float(account["fee_rate"])))
            value, fee = quantity * price, quantity * price * float(account["fee_rate"])
            cost, now = value + fee, _now()
            connection.execute(
                """UPDATE scalp_accounts SET cash_balance=cash_balance-?,quantity=?,entry_price=?,
                entry_cost=?,stop_price=?,target_price=?,updated_at=? WHERE id=?""",
                (cost, quantity, price, cost, price * (1-config["stop_pct"]),
                 price * (1+config["target_pct"]), now, account["id"]),
            )
            connection.execute(
                """INSERT INTO scalp_trades(account_id,opened_at,entry_price,quantity,buy_fee,signal_note)
                VALUES (?,?,?,?,?,?)""",
                (account["id"], now, price, quantity, fee, signal["reason"]),
            )
    return get_scalp_dashboard(account["symbol"], price)


def stop_scalp_account(account_id, current_price):
    with _connect() as connection:
        account = connection.execute("SELECT * FROM scalp_accounts WHERE id=? AND status='ACTIVE'", (int(account_id),)).fetchone()
        if not account:
            raise ValueError("Активный скальпинг-профиль не найден.")
        if float(account["quantity"]) > 0:
            _close_position(connection, account, float(current_price), "MANUAL_STOP")
        now = _now()
        connection.execute("UPDATE scalp_accounts SET status='STOPPED',updated_at=?,ended_at=? WHERE id=?", (now, now, account["id"]))


def get_active_scalp_accounts():
    with _connect() as connection:
        accounts = [dict(row) for row in connection.execute("SELECT * FROM scalp_accounts WHERE status='ACTIVE'").fetchall()]
        for account in accounts:
            account["interval"] = PROFILES[account["profile"]]["interval"]
        return accounts


def get_scalp_dashboard(symbol, current_price=None):
    with _connect() as connection:
        accounts = [dict(row) for row in connection.execute("SELECT * FROM scalp_accounts WHERE symbol=? ORDER BY id DESC", (str(symbol).upper(),)).fetchall()]
        result = []
        for account in accounts:
            trades = [dict(row) for row in connection.execute("SELECT * FROM scalp_trades WHERE account_id=? ORDER BY id DESC LIMIT 20", (account["id"],)).fetchall()]
            closed = [trade for trade in trades if trade["closed_at"]]
            price = float(current_price or account["entry_price"] or 0)
            account["equity"] = float(account["cash_balance"]) + float(account["quantity"]) * price
            account["total_pnl"] = account["equity"] - float(account["initial_balance"])
            account["profile_label"] = PROFILES[account["profile"]]["label"]
            account["interval"] = PROFILES[account["profile"]]["interval"]
            account["trades"] = trades
            account["stats"] = {"closed": len(closed), "wins": sum(float(t["pnl"]) > 0 for t in closed), "pnl": sum(float(t["pnl"]) for t in closed)}
            result.append(account)
        return result
