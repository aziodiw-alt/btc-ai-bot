import base64
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from web.dashboard_trades import (
    sync_bybit_executions,
    sync_pending_orders,
)


API_KEY = os.getenv("BYBIT_API_KEY", "").strip()
PRIVATE_KEY_B64 = os.getenv("BYBIT_RSA_PRIVATE_KEY_B64", "").strip()
BASE_URL = os.getenv("BYBIT_API_BASE", "https://api.bybit.eu").rstrip("/")
REFERER = os.getenv("BYBIT_REFERER", "Cg000971").strip()
SYNC_INTERVAL = max(int(os.getenv("BYBIT_SYNC_INTERVAL", "180")), 60)
RECV_WINDOW = 5000
SYMBOLS = ("BTCUSDT", "ETHUSDT")


class BybitReadOnlyClient:
    def __init__(self):
        if not API_KEY or not PRIVATE_KEY_B64:
            raise ValueError(
                "Не заданы BYBIT_API_KEY и BYBIT_RSA_PRIVATE_KEY_B64."
            )

        private_key_pem = base64.b64decode(PRIVATE_KEY_B64)
        self.private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
        )

    def _sign(self, message):
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def get(self, path, params):
        query_string = urlencode(params)
        timestamp = str(int(time.time() * 1000))
        message = (
            timestamp
            + API_KEY
            + str(RECV_WINDOW)
            + query_string
        )
        headers = {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(RECV_WINDOW),
            "X-BAPI-SIGN": self._sign(message),
            "X-BAPI-SIGN-TYPE": "2",
            "X-Referer": REFERER,
            "User-Agent": "btc-ai-dashboard/1.0",
        }

        response = requests.get(
            f"{BASE_URL}{path}?{query_string}",
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("retCode") != 0:
            raise RuntimeError(
                f'Bybit API {payload.get("retCode")}: '
                f'{payload.get("retMsg", "неизвестная ошибка")}'
            )

        return payload.get("result") or {}

    def get_open_orders(self, symbol):
        result = self.get(
            "/v5/order/realtime",
            {
                "category": "spot",
                "symbol": symbol,
                "openOnly": 0,
                "limit": 50,
            },
        )
        return result.get("list") or []

    def get_recent_executions(self, symbol):
        items = []
        cursor = None

        for _ in range(5):
            params = {
                "category": "spot",
                "symbol": symbol,
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor

            result = self.get("/v5/execution/list", params)
            items.extend(result.get("list") or [])
            cursor = result.get("nextPageCursor")

            if not cursor:
                break

        return items


def _iso_from_milliseconds(value):
    timestamp = int(value or 0) / 1000
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat()


def _map_order(item, symbol):
    price = float(item.get("price") or item.get("orderPrice") or 0)
    quantity = float(item.get("qty") or item.get("orderQty") or 0)
    value = float(item.get("cumExecValue") or 0)

    if value <= 0:
        value = price * quantity

    return {
        "order_id": str(item.get("orderId") or "").strip(),
        "symbol": symbol,
        "side": str(item.get("side") or "").upper(),
        "order_type": str(item.get("orderType") or "LIMIT").upper(),
        "order_value": value,
        "order_price": price,
        "order_quantity": quantity,
        "created_at": _iso_from_milliseconds(item.get("createdTime")),
    }


def _map_execution(item, symbol):
    return {
        "transaction_id": str(item.get("execId") or "").strip(),
        "symbol": symbol,
        "side": str(item.get("side") or "").upper(),
        "order_type": str(item.get("orderType") or "").upper(),
        "fee_coin": str(item.get("feeCurrency") or "").upper(),
        "fee_amount": float(item.get("execFee") or 0),
        "filled_value": float(item.get("execValue") or 0),
        "filled_price": float(item.get("execPrice") or 0),
        "filled_quantity": float(item.get("execQty") or 0),
        "order_id": str(item.get("orderId") or "").strip(),
        "executed_at": _iso_from_milliseconds(item.get("execTime")),
    }


def sync_once(client=None):
    client = client or BybitReadOnlyClient()
    report = {}

    for symbol in SYMBOLS:
        executions = [
            _map_execution(item, symbol)
            for item in client.get_recent_executions(symbol)
            if item.get("execId")
        ]
        execution_report = sync_bybit_executions(
            executions,
            symbol=symbol,
        )

        orders = [
            _map_order(item, symbol)
            for item in client.get_open_orders(symbol)
            if item.get("orderId")
        ]
        order_report = sync_pending_orders(orders, symbol=symbol)

        report[symbol] = {
            "executions": execution_report,
            "orders": order_report,
        }

    return report


def run_forever():
    print(
        f"Автосинхронизация Bybit EU запущена, "
        f"интервал {SYNC_INTERVAL} сек."
    )
    client = None

    while True:
        try:
            client = client or BybitReadOnlyClient()
            report = sync_once(client)
            summary = ", ".join(
                f"{symbol}: "
                f"{data['orders']['open']} орд., "
                f"{data['executions']['added']} новых исполн."
                for symbol, data in report.items()
            )
            print(f"Bybit синхронизирован: {summary}")
        except Exception as error:
            print(f"Ошибка синхронизации Bybit: {error}")

        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    run_forever()
