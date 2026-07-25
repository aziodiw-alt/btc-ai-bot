import json
import os
import sqlite3
from datetime import datetime


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
    return connection


def _signal_type(result):
    grade = str(result.get("grade", "")).upper()
    decision = str(result.get("decision", "")).upper()

    if grade == "SKIP" or decision.startswith("SKIP"):
        return "SKIP"

    if grade == "WAIT" or "WAIT" in decision:
        return "WAIT"

    return "BUY"


def save_snapshot_if_due(result, minimum_interval_seconds=900):
    now = datetime.now()
    now_unix = int(now.timestamp())
    strategy_name = str(result.get("strategy_key", "swing"))

    with _connect() as connection:
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

    return True


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
            WHERE strategy_name IN ('swing', 'fast')
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
                WHERE strategy_name IN ('swing', 'fast')
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

    return [strategies["swing"], strategies["fast"]]
