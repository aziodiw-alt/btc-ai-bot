"""Bybit public market-data adapter."""

import pandas as pd
import requests

from config import BYBIT_BASE_URL, SYMBOL


class BybitMarketDataProvider:
    def __init__(self, base_url=BYBIT_BASE_URL, session=requests):
        self.base_url = str(base_url).rstrip("/")
        self.session = session

    def get_ticker(self, symbol=None):
        response = self.session.get(
            f"{self.base_url}/v5/market/tickers",
            params={"category": "spot", "symbol": symbol or SYMBOL},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data["retCode"] != 0:
            raise Exception(data["retMsg"])

        ticker = data["result"]["list"][0]
        return {
            "price": float(ticker["lastPrice"]),
            "high": float(ticker["highPrice24h"]),
            "low": float(ticker["lowPrice24h"]),
            "volume": float(ticker["volume24h"]),
        }

    def get_klines(self, interval="240", limit=200, symbol=None):
        response = self.session.get(
            f"{self.base_url}/v5/market/kline",
            params={
                "category": "spot",
                "symbol": symbol or SYMBOL,
                "interval": interval,
                "limit": limit,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data["retCode"] != 0:
            raise Exception(data["retMsg"])

        rows = list(reversed(data["result"]["list"]))
        frame = pd.DataFrame(
            rows,
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


__all__ = ["BybitMarketDataProvider"]
