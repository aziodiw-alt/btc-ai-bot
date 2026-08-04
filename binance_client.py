"""Minimal Binance Spot client with account read operations only."""

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests


class BinanceReadOnlyClient:
    def __init__(
        self,
        api_key=None,
        api_secret=None,
        base_url=None,
        session=None,
        clock=None,
    ):
        self.api_key = (api_key or os.getenv("BINANCE_API_KEY", "")).strip()
        self.api_secret = (
            api_secret or os.getenv("BINANCE_API_SECRET", "")
        ).strip()
        self.base_url = (
            base_url
            or os.getenv("BINANCE_API_BASE", "https://api.binance.com")
        ).rstrip("/")
        self.session = session or requests.Session()
        self.clock = clock or time.time

        if not self.api_key or not self.api_secret:
            raise ValueError("Binance credentials are not configured in Railway.")

    def _signed_params(self, params=None):
        signed = dict(params or {})
        signed["timestamp"] = int(self.clock() * 1000)
        signed.setdefault("recvWindow", 5000)
        query = urlencode(signed)
        signed["signature"] = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signed

    def _get(self, path, params=None, *, signed=True):
        request_params = self._signed_params(params) if signed else dict(params or {})
        headers = {
            "X-MBX-APIKEY": self.api_key,
            "User-Agent": "btc-ai-dashboard/1.0",
        }
        response = self.session.get(
            f"{self.base_url}{path}",
            params=request_params,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and int(payload.get("code", 0)) < 0:
            raise RuntimeError(
                f'Binance API {payload.get("code")}: '
                f'{payload.get("msg", "unknown error")}'
            )
        return payload

    def get_account(self):
        return self._get("/api/v3/account", {"omitZeroBalances": "true"})

    def get_open_orders(self, symbol=None):
        params = {"symbol": str(symbol).upper()} if symbol else None
        data = self._get("/api/v3/openOrders", params)
        orders = []
        for item in data:
            price = float(item.get("price") or 0)
            quantity = float(item.get("origQty") or 0)
            executed = float(item.get("executedQty") or 0)
            remaining = max(quantity - executed, 0)
            created_ms = int(item.get("time") or 0)
            orders.append(
                {
                    "order_id": str(item.get("orderId") or ""),
                    "symbol": str(item.get("symbol") or ""),
                    "side": str(item.get("side") or "").upper(),
                    "order_type": str(item.get("type") or "").upper(),
                    "price": price,
                    "quantity": quantity,
                    "executed_quantity": executed,
                    "remaining_quantity": remaining,
                    "remaining_value": price * remaining,
                    "status": str(item.get("status") or "").upper(),
                    "created_at": (
                        datetime.fromtimestamp(
                            created_ms / 1000, tz=timezone.utc
                        ).isoformat()
                        if created_ms else ""
                    ),
                }
            )
        return orders

    def get_trade_history(self, symbol, limit=100):
        data = self._get(
            "/api/v3/myTrades",
            {"symbol": str(symbol).upper(), "limit": int(limit)},
        )
        return [
            {
                "trade_id": str(item.get("id") or ""),
                "order_id": str(item.get("orderId") or ""),
                "symbol": str(item.get("symbol") or symbol).upper(),
                "side": "BUY" if item.get("isBuyer") else "SELL",
                "price": float(item.get("price") or 0),
                "quantity": float(item.get("qty") or 0),
                "value": float(item.get("quoteQty") or 0),
                "fee": float(item.get("commission") or 0),
                "fee_currency": str(item.get("commissionAsset") or ""),
                "created_at": datetime.fromtimestamp(
                    int(item.get("time") or 0) / 1000,
                    tz=timezone.utc,
                ).isoformat(),
            }
            for item in data
        ]

    def connection_status(self):
        account = self.get_account()
        balances = []
        for item in account.get("balances") or []:
            free = float(item.get("free") or 0)
            locked = float(item.get("locked") or 0)
            if free == 0 and locked == 0:
                continue
            balances.append(
                {
                    "currency": str(item.get("asset") or ""),
                    "total": free + locked,
                    "available": free,
                    "locked": locked,
                }
            )
        return {
            "connected": True,
            "base_url": self.base_url,
            "can_read": True,
            "can_trade": bool(account.get("canTrade")),
            "can_withdraw": bool(account.get("canWithdraw")),
            "account_type": str(account.get("accountType") or "SPOT"),
            "currencies": balances,
        }


__all__ = ["BinanceReadOnlyClient"]
