"""OKX public market-data adapter."""

import os

import pandas as pd
import requests

from config import SYMBOL


def normalize_okx_symbol(symbol=None):
    normalized = str(symbol or SYMBOL).replace("/", "").replace("-", "").upper()
    if normalized.endswith("USDT"):
        return normalized[:-4] + "-USDC"
    if normalized.endswith("USDC"):
        return normalized[:-4] + "-USDC"
    return normalized


def normalize_okx_interval(interval):
    return {
        "60": "1H",
        "240": "4H",
        "D": "1Dutc",
    }.get(str(interval), str(interval))


class OkxMarketDataProvider:
    def __init__(self, base_url=None, session=requests):
        self.base_url = str(
            base_url or os.getenv("OKX_API_BASE", "https://eea.okx.com")
        ).rstrip("/")
        self.session = session

    def get_ticker(self, symbol=None):
        response = self.session.get(
            f"{self.base_url}/api/v5/market/ticker",
            params={"instId": normalize_okx_symbol(symbol)},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "0":
            raise Exception(data.get("msg") or "OKX market API error")

        ticker = data["data"][0]
        return {
            "price": float(ticker["last"]),
            "high": float(ticker["high24h"]),
            "low": float(ticker["low24h"]),
            "volume": float(ticker["vol24h"]),
        }

    def get_klines(self, interval="240", limit=200, symbol=None):
        response = self.session.get(
            f"{self.base_url}/api/v5/market/candles",
            params={
                "instId": normalize_okx_symbol(symbol),
                "bar": normalize_okx_interval(interval),
                "limit": min(int(limit), 300),
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "0":
            raise Exception(data.get("msg") or "OKX market API error")

        rows = list(reversed(data["data"]))
        frame = pd.DataFrame(
            [row[:7] for row in rows],
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )
        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = frame[column].astype(float)
        return frame


__all__ = [
    "OkxMarketDataProvider",
    "normalize_okx_interval",
    "normalize_okx_symbol",
]
