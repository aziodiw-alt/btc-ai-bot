import csv
import io
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_FEE_RATE = 0.001
REQUIRED_CSV_COLUMNS = {
    "Spot Pairs",
    "Order Type",
    "Direction",
    "feeCoin",
    "ExecFeeV2",
    "Filled Value",
    "Filled Price",
    "Filled Quantity",
    "Transaction ID",
    "Order No.",
    "Timestamp (UTC)",
}
PROJECT_DIR = Path(__file__).resolve().parent.parent
TELEGRAM_DATABASE_PATH = Path(
    os.getenv(
        "TELEGRAM_DATABASE_PATH",
        str(PROJECT_DIR / "trades.db"),
    )
)


def calculate_sell_advice(
    fifo_stats,
    current_price=None,
    pending_sell_quantity=0,
    fee_rate=DEFAULT_FEE_RATE,
    quote_currency="USDT",
):
    quantity = float(fifo_stats.get("open_quantity") or 0)
    open_cost = float(fifo_stats.get("open_cost") or 0)

    if quantity <= 1e-12 or open_cost <= 0:
        return {
            "available": False,
            "reason": "Нет остатка исполненных покупок для расчёта.",
        }

    average_buy_price = open_cost / quantity
    target_price_15 = (
        average_buy_price * 1.015 / (1 - fee_rate)
    )
    target_price_20 = (
        average_buy_price * 1.020 / (1 - fee_rate)
    )
    reserved_quantity = min(
        max(float(pending_sell_quantity or 0), 0),
        quantity,
    )
    free_quantity = max(quantity - reserved_quantity, 0)
    market_price = (
        float(current_price)
        if current_price is not None
        else None
    )
    free_value_usdt = (
        free_quantity * market_price
        if market_price and market_price > 0
        else None
    )

    return {
        "available": True,
        "quantity": quantity,
        "open_cost": open_cost,
        "average_buy_price": average_buy_price,
        "target_price_15": target_price_15,
        "target_price_20": target_price_20,
        "profit_15": open_cost * 0.015,
        "profit_20": open_cost * 0.020,
        "reserved_quantity": reserved_quantity,
        "free_quantity": free_quantity,
        "free_value_usdt": free_value_usdt,
        "free_value_quote": free_value_usdt,
        "quote_currency": str(quote_currency or "USDT").upper(),
        "current_price": market_price,
        "distance_15_pct": (
            (target_price_15 / market_price - 1) * 100
            if market_price and market_price > 0
            else None
        ),
        "distance_20_pct": (
            (target_price_20 / market_price - 1) * 100
            if market_price and market_price > 0
            else None
        ),
        "fee_rate": fee_rate,
    }


def calculate_okx_fifo_statistics(trades, instrument):
    """Calculate the remaining spot position from normalized OKX fills."""
    instrument = str(instrument or "").upper()
    base_currency, _, quote_currency = instrument.partition("-")
    lots = []
    unmatched_sell_quantity = 0.0

    matching_trades = sorted(
        (
            trade
            for trade in (trades or [])
            if str(trade.get("instrument") or "").upper() == instrument
        ),
        key=lambda trade: str(trade.get("created_at") or ""),
    )

    for trade in matching_trades:
        side = str(trade.get("side") or "").upper()
        size = max(float(trade.get("size") or 0), 0)
        value = max(float(trade.get("value") or 0), 0)
        fee = float(trade.get("fee") or 0)
        fee_currency = str(trade.get("fee_currency") or "").upper()

        if side == "BUY":
            acquired_quantity = size
            cost = value

            if fee_currency == base_currency:
                acquired_quantity = max(size + fee, 0)
            elif fee_currency == quote_currency:
                cost += abs(fee)

            if acquired_quantity > 1e-12 and cost > 0:
                lots.append(
                    {
                        "quantity": acquired_quantity,
                        "unit_cost": cost / acquired_quantity,
                    }
                )
            continue

        if side != "SELL":
            continue

        quantity_to_remove = size
        if fee_currency == base_currency:
            quantity_to_remove += abs(fee)

        while quantity_to_remove > 1e-12 and lots:
            lot = lots[0]
            matched = min(quantity_to_remove, lot["quantity"])
            lot["quantity"] -= matched
            quantity_to_remove -= matched

            if lot["quantity"] <= 1e-12:
                lots.pop(0)

        unmatched_sell_quantity += max(quantity_to_remove, 0)

    open_quantity = sum(lot["quantity"] for lot in lots)
    open_cost = sum(
        lot["quantity"] * lot["unit_cost"]
        for lot in lots
    )

    return {
        "instrument": instrument,
        "execution_count": len(matching_trades),
        "open_quantity": open_quantity,
        "open_cost": open_cost,
        "unmatched_sell_quantity": unmatched_sell_quantity,
    }


def add_okx_order_profit_estimates(
    orders,
    fifo_stats,
    fee_rate=DEFAULT_FEE_RATE,
):
    """Attach FIFO-based expected profit fields to pending OKX orders."""
    enriched_orders = [dict(order) for order in (orders or [])]
    open_quantity = max(
        float(fifo_stats.get("open_quantity") or 0),
        0,
    )
    open_cost = max(float(fifo_stats.get("open_cost") or 0), 0)
    average_buy_price = (
        open_cost / open_quantity
        if open_quantity > 1e-12
        else None
    )
    instrument = str(fifo_stats.get("instrument") or "").upper()
    remaining_position = open_quantity

    for order in enriched_orders:
        order.update(
            {
                "estimated_profit_quote": None,
                "estimated_profit_pct": None,
                "average_buy_price": average_buy_price,
                "matched_quantity": 0.0,
                "profit_coverage_pct": 0.0,
                "profit_is_complete": False,
            }
        )

    sell_indices = sorted(
        (
            index
            for index, order in enumerate(enriched_orders)
            if str(order.get("side") or "").upper() == "SELL"
            and (
                not instrument
                or str(order.get("instrument") or "").upper()
                == instrument
            )
        ),
        key=lambda index: str(
            enriched_orders[index].get("created_at") or ""
        ),
    )

    for index in sell_indices:
        order = enriched_orders[index]
        order_quantity = max(
            float(order.get("remaining_size") or 0),
            0,
        )
        order_price = max(float(order.get("price") or 0), 0)

        if (
            average_buy_price is None
            or order_quantity <= 1e-12
            or order_price <= 0
        ):
            continue

        matched_quantity = min(order_quantity, remaining_position)
        remaining_position = max(
            remaining_position - matched_quantity,
            0,
        )
        coverage_pct = matched_quantity / order_quantity * 100
        is_complete = order_quantity - matched_quantity <= 1e-12

        order["matched_quantity"] = matched_quantity
        order["profit_coverage_pct"] = coverage_pct
        order["profit_is_complete"] = is_complete

        if matched_quantity <= 1e-12:
            continue

        matched_cost = matched_quantity * average_buy_price
        net_proceeds = (
            matched_quantity * order_price * (1 - fee_rate)
        )
        estimated_profit = net_proceeds - matched_cost
        order["estimated_profit_quote"] = estimated_profit
        order["estimated_profit_pct"] = (
            estimated_profit / matched_cost * 100
            if matched_cost > 0
            else None
        )

    return enriched_orders


def _connect():
    if not TELEGRAM_DATABASE_PATH.exists():
        raise ValueError(
            "База Telegram trades.db ещё не создана. "
            "Сначала запустите Telegram-бота."
        )

    connection = sqlite3.connect(TELEGRAM_DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_orders (
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
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(pending_orders)"
        ).fetchall()
    }
    for column_name, column_type in (
        ("strategy_key", "TEXT"),
        ("strategy_confidence", "INTEGER"),
        ("strategy_reason", "TEXT"),
    ):
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE pending_orders ADD COLUMN {column_name} {column_type}"
            )

    execution_table_exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'bybit_executions'
        """
    ).fetchone()
    if execution_table_exists:
        execution_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(bybit_executions)"
            ).fetchall()
        }
        for column_name, column_type in (
            ("strategy_key", "TEXT"),
            ("strategy_confidence", "INTEGER"),
        ):
            if column_name not in execution_columns:
                connection.execute(
                    f"ALTER TABLE bybit_executions "
                    f"ADD COLUMN {column_name} {column_type}"
                )
    _repair_pending_order_values(connection)
    return connection


def _repair_pending_order_values(connection):
    """Исправляет очевидно перепутанные местами цену и сумму ордера."""
    rows = connection.execute(
        """
        SELECT id, order_price, order_value, order_quantity
        FROM pending_orders
        """
    ).fetchall()

    for row in rows:
        price = float(row["order_price"])
        value = float(row["order_value"])
        quantity = float(row["order_quantity"])

        if price <= 0 or value <= 0 or quantity <= 0:
            continue

        direct_error = abs(price * quantity - value) / max(value, 1e-12)
        swapped_error = abs(value * quantity - price) / max(price, 1e-12)

        if direct_error > 0.5 and swapped_error < 0.05:
            connection.execute(
                """
                UPDATE pending_orders
                SET order_price = ?, order_value = ?
                WHERE id = ?
                """,
                (value, price, row["id"]),
            )


def _resolve_user_id(connection):
    configured_user_id = os.getenv("TELEGRAM_USER_ID")

    if configured_user_id:
        return int(configured_user_id)

    rows = connection.execute(
        """
        SELECT telegram_user_id
        FROM trades
        UNION
        SELECT telegram_user_id
        FROM bybit_executions
        ORDER BY telegram_user_id
        """
    ).fetchall()
    user_ids = [int(row["telegram_user_id"]) for row in rows]

    if len(user_ids) == 1:
        return user_ids[0]

    if not user_ids:
        raise ValueError(
            "В базе Telegram пока нет сделок. "
            "Сначала запишите или импортируйте одну сделку через бота."
        )

    raise ValueError(
        "В базе найдено несколько пользователей. "
        "Добавьте TELEGRAM_USER_ID в файл .env."
    )


def add_trade(
    entry_price,
    amount_usdt,
    trade_date,
    status="OPEN",
    sell_price=None,
    notes="",
    symbol="BTCUSDT",
):
    del notes

    normalized_status = str(status).upper()

    if normalized_status not in {"OPEN", "CLOSED"}:
        raise ValueError("Неизвестный статус сделки")

    entry_price = float(entry_price)
    amount_usdt = float(amount_usdt)

    if entry_price <= 0 or amount_usdt <= 0:
        raise ValueError("Цена и сумма сделки должны быть больше нуля")

    normalized_sell_price = None

    if sell_price not in (None, ""):
        normalized_sell_price = float(sell_price)

        if normalized_sell_price <= 0:
            raise ValueError("Цена продажи должна быть больше нуля")

    if normalized_status == "CLOSED" and normalized_sell_price is None:
        raise ValueError("Для закрытой сделки укажите цену продажи")

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        normalized_symbol = str(symbol).replace("/", "").upper()

        if normalized_status == "OPEN":
            existing_open = connection.execute(
                """
                SELECT 1
                FROM trades
                WHERE telegram_user_id = ?
                  AND symbol = ?
                  AND status = 'OPEN'
                LIMIT 1
                """,
                (telegram_user_id, normalized_symbol),
            ).fetchone()

            if existing_open:
                raise ValueError(
                    "Уже есть открытая ручная сделка. "
                    "Сначала закройте её."
                )

        btc_quantity = amount_usdt / entry_price
        opened_at = _normalize_trade_date(trade_date)
        closed_at = None
        gross_pnl = None
        net_pnl = None
        net_pnl_pct = None

        if normalized_status == "CLOSED":
            exit_value = btc_quantity * normalized_sell_price
            entry_fee = amount_usdt * DEFAULT_FEE_RATE
            exit_fee = exit_value * DEFAULT_FEE_RATE
            gross_pnl = exit_value - amount_usdt
            net_pnl = gross_pnl - entry_fee - exit_fee
            net_pnl_pct = net_pnl / amount_usdt * 100
            closed_at = datetime.now(timezone.utc).isoformat()

        connection.execute(
            """
            INSERT INTO trades (
                telegram_user_id,
                symbol,
                entry_price,
                quote_amount,
                btc_quantity,
                fee_rate,
                opened_at,
                exit_price,
                closed_at,
                gross_pnl,
                net_pnl,
                net_pnl_pct,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                normalized_symbol,
                entry_price,
                amount_usdt,
                btc_quantity,
                DEFAULT_FEE_RATE,
                opened_at,
                normalized_sell_price,
                closed_at,
                gross_pnl,
                net_pnl,
                net_pnl_pct,
                normalized_status,
            ),
        )


def _normalize_trade_date(value):
    text = str(value).strip()

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()

    return parsed.astimezone(timezone.utc).isoformat()


def import_bybit_csv(uploaded_file, symbol="BTCUSDT"):
    """Импортирует CSV Bybit в локальную базу сайта без дубликатов."""
    if not uploaded_file or not uploaded_file.filename:
        raise ValueError("Выберите CSV-файл Bybit.")

    if not uploaded_file.filename.lower().endswith(".csv"):
        raise ValueError("Нужен файл с расширением .csv.")

    text_stream = io.TextIOWrapper(
        uploaded_file.stream,
        encoding="utf-8-sig",
        newline="",
    )
    reader = csv.DictReader(text_stream)

    if not reader.fieldnames:
        raise ValueError("CSV пустой или не содержит заголовков.")

    missing = REQUIRED_CSV_COLUMNS.difference(reader.fieldnames)
    if missing:
        raise ValueError(
            "В CSV отсутствуют колонки: " + ", ".join(sorted(missing))
        )

    added = 0
    duplicates = 0
    ignored = 0
    buy_rows = 0
    sell_rows = 0

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)

        for row in reader:
            row_symbol = (row.get("Spot Pairs") or "").strip().upper()
            side = (row.get("Direction") or "").strip().upper()
            transaction_id = (row.get("Transaction ID") or "").strip()

            if (
                row_symbol != symbol
                or side not in {"BUY", "SELL"}
                or not transaction_id
            ):
                ignored += 1
                continue

            try:
                executed_at = datetime.strptime(
                    (row.get("Timestamp (UTC)") or "").strip(),
                    "%H:%M %Y-%m-%d",
                ).replace(tzinfo=timezone.utc).isoformat()

                order_id = (row.get("Order No.") or "").strip()
                strategy_key = None
                strategy_confidence = None

                if order_id:
                    pending_order = connection.execute(
                        """
                        SELECT strategy_key, strategy_confidence
                        FROM pending_orders
                        WHERE telegram_user_id = ? AND order_id = ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (telegram_user_id, order_id),
                    ).fetchone()
                    if pending_order:
                        strategy_key = pending_order["strategy_key"]
                        strategy_confidence = pending_order[
                            "strategy_confidence"
                        ]

                    connection.execute(
                        """
                        DELETE FROM bybit_executions
                        WHERE telegram_user_id = ?
                          AND transaction_id LIKE 'MANUAL-ORDER-%'
                          AND order_id = ?
                        """,
                        (telegram_user_id, order_id),
                    )

                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO bybit_executions (
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
                        executed_at,
                        strategy_key,
                        strategy_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_user_id,
                        transaction_id,
                        row_symbol,
                        side,
                        (row.get("Order Type") or "").strip().upper(),
                        (row.get("feeCoin") or "").strip().upper(),
                        float((row.get("ExecFeeV2") or "0").strip()),
                        float((row.get("Filled Value") or "0").strip()),
                        float((row.get("Filled Price") or "0").strip()),
                        float((row.get("Filled Quantity") or "0").strip()),
                        order_id,
                        executed_at,
                        strategy_key,
                        strategy_confidence,
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Некорректная строка CSV, Transaction ID {transaction_id}: {exc}"
                ) from exc

            if cursor.rowcount:
                added += 1
                if side == "BUY":
                    buy_rows += 1
                else:
                    sell_rows += 1

                if order_id:
                    connection.execute(
                        """
                        UPDATE pending_orders
                        SET status = 'FILLED', updated_at = ?
                        WHERE telegram_user_id = ?
                          AND order_id = ?
                        """,
                        (
                            datetime.now(timezone.utc).isoformat(),
                            telegram_user_id,
                            order_id,
                        ),
                    )
            else:
                duplicates += 1

    return {
        "added": added,
        "duplicates": duplicates,
        "ignored": ignored,
        "buy_rows": buy_rows,
        "sell_rows": sell_rows,
    }


def _normalize_zone(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        first = float(value[0])
        second = float(value[1])
        return min(first, second), max(first, second)

    center = float(value)
    return center, center


def _distance_to_zone_pct(price, zone):
    low, high = zone
    if low <= price <= high:
        return 0.0
    nearest = low if price < low else high
    return abs(price - nearest) / max(price, 1e-12) * 100


def classify_order_strategy(order_price, side, strategy_levels):
    price = float(order_price)
    side = str(side).upper()
    candidates = []

    for strategy_key, result in (strategy_levels or {}).items():
        strategy_name = "Fast" if strategy_key == "fast" else "Swing"

        if side == "BUY":
            for zone_key, zone_label in (
                ("buy_zone_1", "Buy Zone 1"),
                ("buy_zone_2", "Buy Zone 2"),
            ):
                if result.get(zone_key) is None:
                    continue
                zone = _normalize_zone(result[zone_key])
                distance = _distance_to_zone_pct(price, zone)
                center_distance = abs(price - sum(zone) / 2) / price * 100
                candidates.append({
                    "strategy_key": strategy_key,
                    "strategy_name": strategy_name,
                    "distance": distance,
                    "tie_distance": center_distance,
                    "level": zone_label,
                })
        elif side == "SELL":
            for target_key, target_label in (
                ("take_profit_1", "TP1"),
                ("take_profit_2", "TP2"),
            ):
                if result.get(target_key) is None:
                    continue
                target = float(result[target_key])
                distance = abs(price - target) / price * 100
                candidates.append({
                    "strategy_key": strategy_key,
                    "strategy_name": strategy_name,
                    "distance": distance,
                    "tie_distance": distance,
                    "level": target_label,
                })

    if not candidates:
        return {
            "strategy_key": None,
            "strategy_confidence": 0,
            "strategy_reason": "Недостаточно данных для определения",
        }

    candidates.sort(key=lambda item: (item["distance"], item["tie_distance"]))
    best = candidates[0]
    distance = best["distance"]

    if distance == 0:
        confidence = 95
        reason = f"Цена внутри {best['strategy_name']} {best['level']}"
    elif distance <= 0.35:
        confidence = 88
        reason = (
            f"Цена на {distance:.2f}% от "
            f"{best['strategy_name']} {best['level']}"
        )
    elif distance <= 1.0:
        confidence = 70
        reason = (
            f"Цена на {distance:.2f}% от "
            f"{best['strategy_name']} {best['level']}"
        )
    else:
        return {
            "strategy_key": None,
            "strategy_confidence": 0,
            "strategy_reason": (
                f"Ближайший уровень дальше чем на {distance:.2f}%"
            ),
        }

    return {
        "strategy_key": best["strategy_key"],
        "strategy_confidence": confidence,
        "strategy_reason": reason,
    }


def classify_unassigned_orders(strategy_levels, symbol="BTCUSDT"):
    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        rows = connection.execute(
            """
            SELECT id, side, order_price
            FROM pending_orders
            WHERE telegram_user_id = ?
              AND status = 'OPEN'
              AND strategy_key IS NULL
              AND symbol = ?
            """,
            (telegram_user_id, str(symbol).upper()),
        ).fetchall()

        for row in rows:
            classification = classify_order_strategy(
                row["order_price"],
                row["side"],
                strategy_levels,
            )
            connection.execute(
                """
                UPDATE pending_orders
                SET
                    strategy_key = ?,
                    strategy_confidence = ?,
                    strategy_reason = ?
                WHERE id = ? AND telegram_user_id = ?
                """,
                (
                    classification["strategy_key"],
                    classification["strategy_confidence"],
                    classification["strategy_reason"],
                    row["id"],
                    telegram_user_id,
                ),
            )


def has_unassigned_orders(symbol="BTCUSDT"):
    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        row = connection.execute(
            """
            SELECT 1
            FROM pending_orders
            WHERE telegram_user_id = ?
              AND status = 'OPEN'
              AND strategy_key IS NULL
              AND symbol = ?
            LIMIT 1
            """,
            (telegram_user_id, str(symbol).upper()),
        ).fetchone()
    return row is not None


def add_pending_orders(orders, strategy_levels=None):
    if not orders:
        raise ValueError("Нет ордеров для сохранения.")

    saved = 0
    duplicates = 0
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)

        for order in orders:
            side = str(order.get("side", "")).upper()
            if side not in {"BUY", "SELL"}:
                raise ValueError("Сторона ордера должна быть BUY или SELL.")

            order_price = float(order.get("order_price") or 0)
            order_quantity = float(order.get("order_quantity") or 0)
            order_value = float(order.get("order_value") or 0)

            if order_price <= 0 or order_quantity <= 0:
                raise ValueError("Цена и количество ордера должны быть больше нуля.")

            if order_value <= 0:
                order_value = order_price * order_quantity

            direct_error = (
                abs(order_price * order_quantity - order_value)
                / max(order_value, 1e-12)
            )
            swapped_error = (
                abs(order_value * order_quantity - order_price)
                / max(order_price, 1e-12)
            )

            if direct_error > 0.5 and swapped_error < 0.05:
                order_price, order_value = order_value, order_price

            created_at = _normalize_trade_date(
                order.get("created_at")
                or datetime.now().strftime("%Y-%m-%dT%H:%M")
            )
            order_id = str(order.get("order_id") or "").strip() or None
            classification = classify_order_strategy(
                order_price,
                side,
                strategy_levels,
            )

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO pending_orders (
                    telegram_user_id,
                    order_id,
                    symbol,
                    side,
                    order_type,
                    order_value,
                    order_price,
                    order_quantity,
                    created_at,
                    status,
                    updated_at,
                    strategy_key,
                    strategy_confidence,
                    strategy_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    order_id,
                    str(order.get("symbol") or "BTCUSDT")
                    .replace("/", "")
                    .upper(),
                    side,
                    str(order.get("order_type") or "LIMIT").upper(),
                    order_value,
                    order_price,
                    order_quantity,
                    created_at,
                    now,
                    classification["strategy_key"],
                    classification["strategy_confidence"],
                    classification["strategy_reason"],
                ),
            )

            if cursor.rowcount:
                saved += 1
            else:
                duplicates += 1

    return {"saved": saved, "duplicates": duplicates}


def sync_bybit_executions(executions, symbol="BTCUSDT"):
    """Сохраняет исполнения API Bybit и не создаёт дубликаты."""
    symbol = str(symbol).replace("/", "").upper()
    added = 0
    duplicates = 0
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)

        for execution in executions:
            transaction_id = str(
                execution.get("transaction_id") or ""
            ).strip()
            order_id = str(execution.get("order_id") or "").strip()

            if not transaction_id:
                continue

            strategy_key = None
            strategy_confidence = None

            if order_id:
                pending_order = connection.execute(
                    """
                    SELECT strategy_key, strategy_confidence
                    FROM pending_orders
                    WHERE telegram_user_id = ? AND order_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (telegram_user_id, order_id),
                ).fetchone()

                if pending_order:
                    strategy_key = pending_order["strategy_key"]
                    strategy_confidence = pending_order[
                        "strategy_confidence"
                    ]

                connection.execute(
                    """
                    DELETE FROM bybit_executions
                    WHERE telegram_user_id = ?
                      AND transaction_id LIKE 'MANUAL-ORDER-%'
                      AND order_id = ?
                    """,
                    (telegram_user_id, order_id),
                )

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO bybit_executions (
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
                    executed_at,
                    strategy_key,
                    strategy_confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    transaction_id,
                    symbol,
                    str(execution.get("side") or "").upper(),
                    str(execution.get("order_type") or "").upper(),
                    str(execution.get("fee_coin") or "").upper(),
                    float(execution.get("fee_amount") or 0),
                    float(execution.get("filled_value") or 0),
                    float(execution.get("filled_price") or 0),
                    float(execution.get("filled_quantity") or 0),
                    order_id,
                    str(execution.get("executed_at") or now),
                    strategy_key,
                    strategy_confidence,
                ),
            )

            if cursor.rowcount:
                added += 1
            else:
                duplicates += 1

            if order_id:
                connection.execute(
                    """
                    UPDATE pending_orders
                    SET status = 'FILLED', updated_at = ?
                    WHERE telegram_user_id = ? AND order_id = ?
                    """,
                    (now, telegram_user_id, order_id),
                )

    return {
        "added": added,
        "duplicates": duplicates,
        "received": len(executions),
    }


def sync_pending_orders(orders, symbol="BTCUSDT"):
    """Полностью синхронизирует текущие открытые ордера одного символа."""
    symbol = str(symbol).replace("/", "").upper()
    now = datetime.now(timezone.utc).isoformat()
    active_order_ids = []
    saved = 0
    updated = 0

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)

        for order in orders:
            order_id = str(order.get("order_id") or "").strip()
            side = str(order.get("side") or "").upper()
            price = float(order.get("order_price") or 0)
            quantity = float(order.get("order_quantity") or 0)
            value = float(order.get("order_value") or price * quantity)

            if (
                not order_id
                or side not in {"BUY", "SELL"}
                or price <= 0
                or quantity <= 0
            ):
                continue

            active_order_ids.append(order_id)
            existing = connection.execute(
                """
                SELECT id
                FROM pending_orders
                WHERE telegram_user_id = ? AND order_id = ?
                """,
                (telegram_user_id, order_id),
            ).fetchone()

            connection.execute(
                """
                INSERT INTO pending_orders (
                    telegram_user_id,
                    order_id,
                    symbol,
                    side,
                    order_type,
                    order_value,
                    order_price,
                    order_quantity,
                    created_at,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
                ON CONFLICT(telegram_user_id, order_id)
                DO UPDATE SET
                    symbol = excluded.symbol,
                    side = excluded.side,
                    order_type = excluded.order_type,
                    order_value = excluded.order_value,
                    order_price = excluded.order_price,
                    order_quantity = excluded.order_quantity,
                    status = 'OPEN',
                    updated_at = excluded.updated_at
                """,
                (
                    telegram_user_id,
                    order_id,
                    symbol,
                    side,
                    str(order.get("order_type") or "LIMIT").upper(),
                    value,
                    price,
                    quantity,
                    str(order.get("created_at") or now),
                    now,
                ),
            )

            if existing:
                updated += 1
            else:
                saved += 1

        if active_order_ids:
            placeholders = ",".join("?" for _ in active_order_ids)
            cursor = connection.execute(
                f"""
                UPDATE pending_orders
                SET status = 'CANCELLED', updated_at = ?
                WHERE telegram_user_id = ?
                  AND symbol = ?
                  AND status = 'OPEN'
                  AND order_id NOT IN ({placeholders})
                """,
                (
                    now,
                    telegram_user_id,
                    symbol,
                    *active_order_ids,
                ),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE pending_orders
                SET status = 'CANCELLED', updated_at = ?
                WHERE telegram_user_id = ?
                  AND symbol = ?
                  AND status = 'OPEN'
                """,
                (now, telegram_user_id, symbol),
            )

    return {
        "open": len(active_order_ids),
        "saved": saved,
        "updated": updated,
        "closed": cursor.rowcount,
    }


def fill_pending_order(pending_order_id):
    """Помечает ордер исполненным и создаёт временное исполнение для статистики."""
    pending_order_id = int(pending_order_id)

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        order = connection.execute(
            """
            SELECT *
            FROM pending_orders
            WHERE id = ? AND telegram_user_id = ?
            """,
            (pending_order_id, telegram_user_id),
        ).fetchone()

        if not order:
            raise ValueError("Открытый ордер не найден.")

        if order["status"] != "OPEN":
            raise ValueError("Этот ордер уже не является открытым.")

        side = order["side"].upper()
        quantity = float(order["order_quantity"])
        value = float(order["order_value"])

        base_coin = str(order["symbol"]).upper().removesuffix("USDT")

        if side == "BUY":
            fee_coin = base_coin
            fee_amount = quantity * DEFAULT_FEE_RATE
        else:
            fee_coin = "USDT"
            fee_amount = value * DEFAULT_FEE_RATE

        executed_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT OR IGNORE INTO bybit_executions (
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
                executed_at,
                strategy_key,
                strategy_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                f"MANUAL-ORDER-{pending_order_id}",
                order["symbol"],
                side,
                order["order_type"],
                fee_coin,
                fee_amount,
                value,
                float(order["order_price"]),
                quantity,
                order["order_id"],
                executed_at,
                order["strategy_key"],
                order["strategy_confidence"],
            ),
        )
        connection.execute(
            """
            UPDATE pending_orders
            SET status = 'FILLED', updated_at = ?
            WHERE id = ? AND telegram_user_id = ?
            """,
            (executed_at, pending_order_id, telegram_user_id),
        )


def cancel_pending_order(pending_order_id):
    """Marks a cancelled exchange order without creating an execution."""
    pending_order_id = int(pending_order_id)

    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        order = connection.execute(
            """
            SELECT status
            FROM pending_orders
            WHERE id = ? AND telegram_user_id = ?
            """,
            (pending_order_id, telegram_user_id),
        ).fetchone()

        if not order:
            raise ValueError("Открытый ордер не найден.")

        if order["status"] != "OPEN":
            raise ValueError("Этот ордер уже не является открытым.")

        connection.execute(
            """
            UPDATE pending_orders
            SET status = 'CANCELLED', updated_at = ?
            WHERE id = ? AND telegram_user_id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                pending_order_id,
                telegram_user_id,
            ),
        )


def get_pending_orders(
    current_price=None,
    limit=100,
    symbol="BTCUSDT",
):
    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        rows = connection.execute(
            """
            SELECT *
            FROM pending_orders
            WHERE telegram_user_id = ? AND symbol = ?
            ORDER BY
                CASE status WHEN 'OPEN' THEN 0 ELSE 1 END,
                created_at DESC,
                id DESC
            LIMIT ?
            """,
            (telegram_user_id, str(symbol).upper(), int(limit)),
        ).fetchall()
        fifo_stats = _get_bybit_fifo_statistics(
            connection,
            telegram_user_id,
            symbol,
        )

    open_quantity = float(fifo_stats["open_quantity"] or 0)
    open_cost = float(fifo_stats["open_cost"] or 0)
    average_buy_price = (
        open_cost / open_quantity
        if open_quantity > 1e-12
        else None
    )
    market_price = (
        float(current_price)
        if current_price is not None
        else None
    )

    items = []
    remaining_open_quantity = open_quantity

    for row in rows:
        order = dict(row)
        order_price = float(order["order_price"])
        order_quantity = float(order["order_quantity"])
        side = str(order["side"]).upper()

        order["distance_pct"] = None
        order["estimated_profit_usdt"] = None
        order["estimated_profit_pct"] = None
        order["estimated_cost_usdt"] = None
        order["matched_quantity"] = 0.0
        order["unmatched_quantity"] = 0.0
        order["profit_coverage_pct"] = None
        order["profit_is_complete"] = False
        order["average_buy_price"] = (
            average_buy_price if side == "SELL" else None
        )
        if side == "SELL":
            order["unmatched_quantity"] = order_quantity
            order["profit_coverage_pct"] = 0.0

        if market_price and market_price > 0:
            if side == "BUY":
                order["distance_pct"] = (
                    (market_price - order_price)
                    / market_price
                    * 100
                )
            elif side == "SELL":
                order["distance_pct"] = (
                    (order_price - market_price)
                    / market_price
                    * 100
                )

        if (
            side == "SELL"
            and average_buy_price is not None
            and order_quantity > 0
            and remaining_open_quantity > 1e-12
        ):
            matched_quantity = min(
                order_quantity,
                remaining_open_quantity,
            )
            remaining_open_quantity = max(
                remaining_open_quantity - matched_quantity,
                0,
            )
            entry_value = matched_quantity * average_buy_price
            exit_value = matched_quantity * order_price
            # average_buy_price is derived from FIFO unit_cost, which
            # already includes the entry fee. Only the future sell fee
            # must be subtracted here.
            estimated_sell_fee = exit_value * DEFAULT_FEE_RATE
            estimated_profit = (
                exit_value
                - entry_value
                - estimated_sell_fee
            )

            order["matched_quantity"] = matched_quantity
            order["unmatched_quantity"] = max(
                order_quantity - matched_quantity,
                0,
            )
            order["profit_coverage_pct"] = (
                matched_quantity / order_quantity * 100
            )
            order["profit_is_complete"] = (
                order["unmatched_quantity"] <= 1e-12
            )
            order["estimated_cost_usdt"] = entry_value
            order["estimated_profit_usdt"] = estimated_profit
            order["estimated_profit_pct"] = (
                estimated_profit / entry_value * 100
                if entry_value > 0
                else None
            )

        items.append(order)

    return items


def _get_bybit_fifo_statistics(
    connection,
    telegram_user_id,
    symbol="BTCUSDT",
):
    rows = connection.execute(
        """
        SELECT *
        FROM bybit_executions
        WHERE telegram_user_id = ? AND symbol = ?
        ORDER BY executed_at ASC, id ASC
        """,
        (telegram_user_id, str(symbol).upper()),
    ).fetchall()
    lots = []
    closed_results = []
    unmatched_sell_quantity = 0.0
    base_coin = str(symbol).upper().removesuffix("USDT")

    for row in rows:
        quantity = float(row["filled_quantity"])
        value = float(row["filled_value"])
        fee = float(row["fee_amount"])
        fee_coin = (row["fee_coin"] or "").upper()
        side = row["side"].upper()

        if side == "BUY":
            net_quantity = (
                quantity - fee
                if fee_coin == base_coin
                else quantity
            )
            quote_cost = value + fee if fee_coin in {"USDT", "USDC"} else value

            if net_quantity > 0:
                lots.append(
                    {
                        "quantity": net_quantity,
                        "unit_cost": quote_cost / net_quantity,
                        "opened_at": row["executed_at"],
                        "strategy_key": row["strategy_key"],
                        "strategy_confidence": row["strategy_confidence"],
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
        matched_opened_at = None
        matched_strategies = {}
        matched_confidence_total = 0.0

        while remaining > 1e-12 and lots:
            lot = lots[0]
            matched = min(remaining, lot["quantity"])

            if matched_opened_at is None:
                matched_opened_at = lot["opened_at"]

            matched_cost += matched * lot["unit_cost"]
            matched_proceeds += matched * unit_proceeds
            matched_quantity += matched
            strategy_key = lot.get("strategy_key")
            if strategy_key:
                matched_strategies[strategy_key] = (
                    matched_strategies.get(strategy_key, 0.0) + matched
                )
                matched_confidence_total += (
                    matched * float(lot.get("strategy_confidence") or 0)
                )
            lot["quantity"] -= matched
            remaining -= matched

            if lot["quantity"] <= 1e-12:
                lots.pop(0)

        unmatched_sell_quantity += max(remaining, 0.0)

        if matched_quantity > 0:
            pnl = matched_proceeds - matched_cost
            cycle_strategy = None
            cycle_confidence = 0

            if matched_strategies:
                sorted_strategies = sorted(
                    matched_strategies.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
                dominant_strategy, dominant_quantity = sorted_strategies[0]
                known_quantity = sum(matched_strategies.values())

                if dominant_quantity / known_quantity >= 0.6:
                    cycle_strategy = dominant_strategy
                else:
                    cycle_strategy = "mixed"

                cycle_confidence = round(
                    matched_confidence_total / known_quantity
                )
            elif row["strategy_key"]:
                cycle_strategy = row["strategy_key"]
                cycle_confidence = int(row["strategy_confidence"] or 0)

            closed_results.append(
                {
                    "opened_at": matched_opened_at,
                    "closed_at": row["executed_at"],
                    "entry_price": (
                        matched_cost / matched_quantity
                        if matched_quantity
                        else 0.0
                    ),
                    "exit_price": unit_proceeds,
                    "quantity": matched_quantity,
                    "entry_cost": matched_cost,
                    "exit_proceeds": matched_proceeds,
                    "pnl": pnl,
                    "strategy_key": cycle_strategy,
                    "strategy_confidence": cycle_confidence,
                    "pnl_pct": (
                        pnl / matched_cost * 100
                        if matched_cost
                        else 0.0
                    ),
                }
            )

    open_quantity = sum(lot["quantity"] for lot in lots)
    open_cost = sum(
        lot["quantity"] * lot["unit_cost"]
        for lot in lots
    )
    wins = sum(1 for item in closed_results if item["pnl"] > 0)

    return {
        "execution_count": len(rows),
        "closed_count": len(closed_results),
        "wins": wins,
        "total_net_pnl": sum(
            item["pnl"]
            for item in closed_results
        ),
        "open_quantity": open_quantity,
        "open_cost": open_cost,
        "unmatched_sell_quantity": unmatched_sell_quantity,
        "cycles": list(reversed(closed_results[-20:])),
    }


def get_trades(
    current_price=None,
    limit=100,
    symbol="BTCUSDT",
):
    with _connect() as connection:
        telegram_user_id = _resolve_user_id(connection)
        rows = connection.execute(
            """
            SELECT *
            FROM trades
            WHERE telegram_user_id = ? AND symbol = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (telegram_user_id, str(symbol).upper(), int(limit)),
        ).fetchall()
        bybit = _get_bybit_fifo_statistics(
            connection,
            telegram_user_id,
            symbol,
        )
        recent_executions = connection.execute(
            """
            SELECT
                executed_at,
                side,
                filled_price,
                filled_quantity,
                filled_value,
                fee_amount,
                fee_coin,
                strategy_key,
                strategy_confidence
            FROM bybit_executions
            WHERE telegram_user_id = ? AND symbol = ?
            ORDER BY executed_at DESC, id DESC
            LIMIT 20
            """,
            (telegram_user_id, str(symbol).upper()),
        ).fetchall()

    items = []
    manual_closed_count = 0
    manual_wins = 0
    manual_net_pnl = 0.0

    for row in rows:
        trade = dict(row)
        is_open = trade["status"] == "OPEN"

        if is_open and current_price is not None:
            exit_value = trade["btc_quantity"] * float(current_price)
            entry_fee = trade["quote_amount"] * trade["fee_rate"]
            exit_fee = exit_value * trade["fee_rate"]
            profit_usdt = (
                exit_value
                - trade["quote_amount"]
                - entry_fee
                - exit_fee
            )
            profit_pct = profit_usdt / trade["quote_amount"] * 100
        else:
            profit_usdt = trade["net_pnl"]
            profit_pct = trade["net_pnl_pct"]

        trade["trade_date"] = trade["opened_at"]
        trade["amount_usdt"] = trade["quote_amount"]
        trade["sell_price"] = trade["exit_price"]
        trade["profit_usdt"] = profit_usdt
        trade["profit_pct"] = profit_pct
        trade["btc_amount"] = trade["btc_quantity"]
        trade["notes"] = "Ручная сделка Telegram / сайт"
        trade["source"] = "MANUAL"
        items.append(trade)

        if not is_open:
            manual_closed_count += 1
            manual_net_pnl += float(trade["net_pnl"] or 0)

            if float(trade["net_pnl"] or 0) > 0:
                manual_wins += 1

    total_closed = manual_closed_count + bybit["closed_count"]
    total_wins = manual_wins + bybit["wins"]
    total_net_pnl = manual_net_pnl + bybit["total_net_pnl"]

    return {
        "items": items,
        "executions": [dict(row) for row in recent_executions],
        "cycles": bybit["cycles"],
        "bybit": bybit,
        "stats": {
            "total": len(items) + bybit["execution_count"],
            "open_count": (
                sum(1 for item in items if item["status"] == "OPEN")
                + (1 if bybit["open_quantity"] > 0 else 0)
            ),
            "closed_count": total_closed,
            "open_value_usdt": (
                sum(
                    item["quote_amount"]
                    for item in items
                    if item["status"] == "OPEN"
                )
                + bybit["open_cost"]
            ),
            "closed_profit_usdt": total_net_pnl,
            "win_rate": (
                total_wins / total_closed * 100
                if total_closed
                else 0.0
            ),
        },
    }
