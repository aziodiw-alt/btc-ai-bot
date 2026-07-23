import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from database import (
    get_bybit_fifo_statistics,
    insert_bybit_execution,
)


REQUIRED_COLUMNS = {
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


def _decimal(value, field_name):
    try:
        return float(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Некорректное значение в колонке {field_name}")


def _parse_timestamp(value):
    parsed = datetime.strptime(value.strip(), "%H:%M %Y-%m-%d")
    return parsed.replace(tzinfo=timezone.utc).isoformat()


def import_bybit_csv(file_path, telegram_user_id, symbol="BTCUSDT"):
    added = 0
    duplicates = 0
    ignored = 0
    buy_rows = 0
    sell_rows = 0

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            raise ValueError("CSV пустой или не содержит заголовков.")

        missing = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing:
            raise ValueError(
                "Не найдены обязательные колонки: " + ", ".join(sorted(missing))
            )

        for row in reader:
            row_symbol = (row.get("Spot Pairs") or "").strip().upper()
            side = (row.get("Direction") or "").strip().upper()

            if row_symbol != symbol or side not in {"BUY", "SELL"}:
                ignored += 1
                continue

            transaction_id = (row.get("Transaction ID") or "").strip()
            if not transaction_id:
                ignored += 1
                continue

            execution = {
                "transaction_id": transaction_id,
                "symbol": row_symbol,
                "side": side,
                "order_type": (row.get("Order Type") or "").strip().upper(),
                "fee_coin": (row.get("feeCoin") or "").strip().upper(),
                "fee_amount": _decimal(row.get("ExecFeeV2"), "ExecFeeV2"),
                "filled_value": _decimal(row.get("Filled Value"), "Filled Value"),
                "filled_price": _decimal(row.get("Filled Price"), "Filled Price"),
                "filled_quantity": _decimal(
                    row.get("Filled Quantity"), "Filled Quantity"
                ),
                "order_id": (row.get("Order No.") or "").strip(),
                "executed_at": _parse_timestamp(row.get("Timestamp (UTC)") or ""),
            }

            if insert_bybit_execution(telegram_user_id, execution):
                added += 1
                if side == "BUY":
                    buy_rows += 1
                else:
                    sell_rows += 1
            else:
                duplicates += 1

    statistics = get_bybit_fifo_statistics(telegram_user_id, symbol)

    return {
        "added": added,
        "duplicates": duplicates,
        "ignored": ignored,
        "buy_rows": buy_rows,
        "sell_rows": sell_rows,
        "statistics": statistics,
    }
