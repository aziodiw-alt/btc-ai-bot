import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone

import requests


class OkxReadOnlyClient:
    """Minimal OKX client restricted to read-only account requests."""

    def __init__(
        self,
        api_key=None,
        api_secret=None,
        passphrase=None,
        base_url=None,
        session=None,
    ):
        self.api_key = (api_key or os.getenv("OKX_API_KEY", "")).strip()
        self.api_secret = (
            api_secret or os.getenv("OKX_API_SECRET", "")
        ).strip()
        self.passphrase = (
            passphrase or os.getenv("OKX_API_PASSPHRASE", "")
        ).strip()
        self.base_url = (
            base_url
            or os.getenv("OKX_API_BASE", "https://openapi.okx.com")
        ).rstrip("/")
        self.session = session or requests.Session()

        if not self.api_key or not self.api_secret or not self.passphrase:
            raise ValueError(
                "OKX credentials are not configured in Railway."
            )

    @staticmethod
    def _timestamp():
        now = datetime.now(timezone.utc)
        return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _signature(self, timestamp, method, request_path, body=""):
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        digest = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("ascii")

    def get(self, request_path):
        timestamp = self._timestamp()
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": self._signature(
                timestamp,
                "GET",
                request_path,
            ),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "btc-ai-dashboard/1.0",
        }
        response = self.session.get(
            f"{self.base_url}{request_path}",
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("code") != "0":
            raise RuntimeError(
                f'OKX API {payload.get("code")}: '
                f'{payload.get("msg", "unknown error")}'
            )

        return payload.get("data") or []

    def get_account_config(self):
        data = self.get("/api/v5/account/config")
        return data[0] if data else {}

    def get_balance(self):
        data = self.get("/api/v5/account/balance")
        return data[0] if data else {}

    def connection_status(self):
        config = self.get_account_config()
        balance = self.get_balance()
        currencies = []

        for detail in balance.get("details") or []:
            total = float(detail.get("eq") or detail.get("cashBal") or 0)
            available = float(detail.get("availBal") or 0)
            if total == 0 and available == 0:
                continue
            currencies.append(
                {
                    "currency": detail.get("ccy"),
                    "total": total,
                    "available": available,
                }
            )

        return {
            "connected": True,
            "base_url": self.base_url,
            "permission": config.get("perm", ""),
            "account_type": config.get("acctLv", config.get("type", "")),
            "currencies": currencies,
        }
