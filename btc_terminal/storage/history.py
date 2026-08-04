"""SQLite repository for persisted dashboard analysis history."""

import json
import os
import sqlite3
from datetime import datetime

from btc_terminal.core.constants import HISTORY_SNAPSHOT_INTERVAL_SECONDS


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATABASE_PATH = os.getenv(
    "DASHBOARD_DATABASE_PATH",
    os.path.join(DATA_DIR, "dashboard.db"),
)


def _connect():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_history (
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
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(analysis_history)"
        ).fetchall()
    }
    if "strategy_name" not in columns:
        connection.execute(
            """
            ALTER TABLE analysis_history
            ADD COLUMN strategy_name TEXT NOT NULL DEFAULT 'swing'
            """
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS analysis_history_created_idx
        ON analysis_history(created_at_unix DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_signal_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_at_unix INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            exchange TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal_price REAL NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit_1 REAL NOT NULL,
            take_profit_2 REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'NOT_TRIGGERED',
            score INTEGER NOT NULL,
            grade TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS strategy_signal_lookup_idx
        ON strategy_signal_outcomes(
            exchange, strategy_name, symbol, resolved_at, created_at_unix DESC
        )
        """
    )
    return connection


def _update_open_signal(connection, result, now, now_unix):
    exchange = str(result.get("exchange", "bybit"))
    strategy_name = str(result.get("strategy_key", "swing"))
    symbol = str(result.get("display_symbol", "BTC/USDT"))
    price = float(result["price"])
    rows = connection.execute(
        """
        SELECT * FROM strategy_signal_outcomes
        WHERE exchange = ? AND strategy_name = ? AND symbol = ?
          AND resolved_at IS NULL
        ORDER BY created_at_unix
        """,
        (exchange, strategy_name, symbol),
    ).fetchall()

    for row in rows:
        status = str(row["status"])
        resolved_at = None
        age_seconds = now_unix - int(row["created_at_unix"])
        expiry_seconds = 2 * 86400 if strategy_name == "fast" else 14 * 86400

        if status == "NOT_TRIGGERED" and age_seconds >= expiry_seconds:
            resolved_at = now.isoformat()
        elif status == "NOT_TRIGGERED" and price <= float(row["entry_price"]):
            status = "ACTIVE"

        if status in ("ACTIVE", "TP1"):
            if price <= float(row["stop_loss"]):
                status = "STOP"
                resolved_at = now.isoformat()
            elif price >= float(row["take_profit_2"]):
                status = "TP2"
                resolved_at = now.isoformat()
            elif price >= float(row["take_profit_1"]):
                status = "TP1"

        connection.execute(
            """
            UPDATE strategy_signal_outcomes
            SET status = ?, updated_at = ?, resolved_at = ?
            WHERE id = ?
            """,
            (status, now.isoformat(), resolved_at, row["id"]),
        )


def _register_signal_if_needed(connection, result, now, now_unix):
    if _signal_type(result) == "SKIP":
        return
    required = ("planned_entry", "stop_loss", "take_profit_1", "take_profit_2")
    if any(result.get(key) is None for key in required):
        return

    identity = (
        str(result.get("exchange", "bybit")),
        str(result.get("strategy_key", "swing")),
        str(result.get("display_symbol", "BTC/USDT")),
    )
    active = connection.execute(
        """
        SELECT 1 FROM strategy_signal_outcomes
        WHERE exchange = ? AND strategy_name = ? AND symbol = ?
          AND resolved_at IS NULL
        LIMIT 1
        """,
        identity,
    ).fetchone()
    if active:
        return

    entry_price = float(result["planned_entry"])
    status = "ACTIVE" if float(result["price"]) <= entry_price else "NOT_TRIGGERED"
    connection.execute(
        """
        INSERT INTO strategy_signal_outcomes (
            created_at, created_at_unix, updated_at, exchange,
            strategy_name, symbol, signal_price, entry_price, stop_loss,
            take_profit_1, take_profit_2, status, score, grade
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now.isoformat(), now_unix, now.isoformat(), *identity,
            float(result["price"]), entry_price, float(result["stop_loss"]),
            float(result["take_profit_1"]), float(result["take_profit_2"]),
            status, int(result["total_score"]), str(result["grade"]),
        ),
    )


def _signal_type(result):
    grade = str(result.get("grade", "")).upper()
    decision = str(result.get("decision", "")).upper()

    if grade == "SKIP" or decision.startswith("SKIP"):
        return "SKIP"

    if grade == "WAIT" or "WAIT" in decision:
        return "WAIT"

    return "BUY"


def save_snapshot_if_due(
    result,
    minimum_interval_seconds=HISTORY_SNAPSHOT_INTERVAL_SECONDS,
):
    now = datetime.now()
    now_unix = int(now.timestamp())
    strategy_name = str(result.get("strategy_key", "swing"))

    with _connect() as connection:
        _update_open_signal(connection, result, now, now_unix)
        latest = connection.execute(
            """
            SELECT created_at_unix
            FROM analysis_history
            WHERE strategy_name = ? AND symbol = ?
            ORDER BY created_at_unix DESC
            LIMIT 1
            """,
            (
                strategy_name,
                str(result.get("display_symbol", "BTC/USDT")),
            ),
        ).fetchone()

        if (
            latest is not None
            and now_unix - latest["created_at_unix"] < minimum_interval_seconds
        ):
            return False

        connection.execute(
            """
            INSERT INTO analysis_history (
                created_at,
                created_at_unix,
                symbol,
                price,
                total_score,
                grade,
                decision,
                signal_type,
                trend_score,
                entry_score,
                indicators_score,
                sentiment_score,
                rsi_4h,
                reasons_json,
                warnings_json
                , strategy_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now.strftime("%d.%m.%Y %H:%M"),
                now_unix,
                str(result.get("display_symbol", "BTC/USDT")),
                float(result["price"]),
                int(result["total_score"]),
                str(result["grade"]),
                str(result["decision"]),
                _signal_type(result),
                int(result["trend_score"]),
                int(result["entry_score"]),
                int(result["indicators_score"]),
                int(result["sentiment_score"]),
                float(result.get("rsi_4h", 0)),
                json.dumps(result.get("reasons", []), ensure_ascii=False),
                json.dumps(result.get("warnings", []), ensure_ascii=False),
                strategy_name,
            ),
        )
        _register_signal_if_needed(connection, result, now, now_unix)

    return True


def get_strategy_effectiveness(strategy_name, symbol, exchange):
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM strategy_signal_outcomes
            WHERE strategy_name = ? AND symbol = ? AND exchange = ?
            ORDER BY created_at_unix DESC
            LIMIT 30
            """,
            (str(strategy_name), str(symbol), str(exchange)),
        ).fetchall()

    items = [dict(row) for row in rows]
    counts = {
        key: sum(item["status"] == key for item in items)
        for key in ("NOT_TRIGGERED", "ACTIVE", "TP1", "TP2", "STOP")
    }
    completed = counts["TP2"] + counts["STOP"]
    win_rate = round(counts["TP2"] / completed * 100, 1) if completed else None
    if completed < 5:
        commentary = "Пока недостаточно завершённых сценариев для надёжной оценки стратегии."
    elif win_rate >= 60:
        commentary = "Стратегия показывает устойчивую долю успешных завершённых сценариев."
    elif win_rate >= 40:
        commentary = "Результат смешанный: параметры стратегии пока рано усиливать или ослаблять."
    else:
        commentary = "Доля успешных сценариев низкая; перед изменением правил нужно изучить причины Stop."
    return {
        "items": items,
        "total": len(items),
        "counts": counts,
        "completed": completed,
        "win_rate": win_rate,
        "commentary": commentary,
    }


def get_dashboard_history(
    limit=20,
    strategy_name="swing",
    symbol="BTC/USDT",
):
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                created_at,
                symbol,
                price,
                total_score,
                grade,
                decision,
                signal_type
            FROM analysis_history
            WHERE strategy_name = ? AND symbol = ?
            ORDER BY created_at_unix DESC
            LIMIT ?
            """,
            (str(strategy_name), str(symbol), int(limit)),
        ).fetchall()

        stats = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(ROUND(AVG(total_score), 1), 0) AS average_score,
                SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) AS buy_count,
                SUM(CASE WHEN signal_type = 'WAIT' THEN 1 ELSE 0 END) AS wait_count,
                SUM(CASE WHEN signal_type = 'SKIP' THEN 1 ELSE 0 END) AS skip_count
            FROM analysis_history
            WHERE strategy_name = ? AND symbol = ?
            """,
            (str(strategy_name), str(symbol)),
        ).fetchone()

    return {
        "items": [dict(row) for row in rows],
        "stats": {
            "total": int(stats["total"] or 0),
            "average_score": float(stats["average_score"] or 0),
            "buy_count": int(stats["buy_count"] or 0),
            "wait_count": int(stats["wait_count"] or 0),
            "skip_count": int(stats["skip_count"] or 0),
        },
    }


def get_strategy_comparison(symbol="BTC/USDT"):
    strategies = {
        "swing": {
            "key": "swing",
            "name": "Swing",
            "total": 0,
            "average_score": 0.0,
            "buy_count": 0,
            "wait_count": 0,
            "skip_count": 0,
            "latest_grade": "—",
            "latest_score": 0,
            "latest_created_at": "—",
        },
        "fast": {
            "key": "fast",
            "name": "Fast",
            "total": 0,
            "average_score": 0.0,
            "buy_count": 0,
            "wait_count": 0,
            "skip_count": 0,
            "latest_grade": "—",
            "latest_score": 0,
            "latest_created_at": "—",
        },
        "alpha": {
            "key": "alpha",
            "name": "Alpha",
            "total": 0,
            "average_score": 0.0,
            "buy_count": 0,
            "wait_count": 0,
            "skip_count": 0,
            "latest_grade": "—",
            "latest_score": 0,
            "latest_created_at": "—",
        },
    }

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                strategy_name,
                COUNT(*) AS total,
                COALESCE(ROUND(AVG(total_score), 1), 0) AS average_score,
                SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) AS buy_count,
                SUM(CASE WHEN signal_type = 'WAIT' THEN 1 ELSE 0 END) AS wait_count,
                SUM(CASE WHEN signal_type = 'SKIP' THEN 1 ELSE 0 END) AS skip_count
            FROM analysis_history
            WHERE strategy_name IN ('swing', 'fast', 'alpha')
              AND symbol = ?
            GROUP BY strategy_name
            """,
            (str(symbol),),
        ).fetchall()

        latest_rows = connection.execute(
            """
            SELECT
                history.strategy_name,
                history.grade,
                history.total_score,
                history.created_at
            FROM analysis_history AS history
            INNER JOIN (
                SELECT strategy_name, MAX(created_at_unix) AS latest_unix
                FROM analysis_history
                WHERE strategy_name IN ('swing', 'fast', 'alpha')
                  AND symbol = ?
                GROUP BY strategy_name
            ) AS latest
                ON latest.strategy_name = history.strategy_name
                AND latest.latest_unix = history.created_at_unix
            """,
            (str(symbol),),
        ).fetchall()

    for row in rows:
        key = str(row["strategy_name"])
        if key not in strategies:
            continue

        strategies[key].update({
            "total": int(row["total"] or 0),
            "average_score": float(row["average_score"] or 0),
            "buy_count": int(row["buy_count"] or 0),
            "wait_count": int(row["wait_count"] or 0),
            "skip_count": int(row["skip_count"] or 0),
        })

    for row in latest_rows:
        key = str(row["strategy_name"])
        if key not in strategies:
            continue

        strategies[key].update({
            "latest_grade": str(row["grade"]),
            "latest_score": int(row["total_score"]),
            "latest_created_at": str(row["created_at"]),
        })

    return [strategies["swing"], strategies["fast"], strategies["alpha"]]
