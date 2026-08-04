"""Binance public Spot market-data adapter."""

import os

import pandas as pd
import requests

from config import SYMBOL


def normalize_binance_interval(interval):
    return {"60": "1h", "240": "4h", "D": "1d"}.get(
        str(interval), str(interval)
    )


class BinanceMarketDataProvider:
    def __init__(self, base_url=None, session=requests):
        self.base_url = str(
            base_url or os.getenv("BINANCE_API_BASE", "https://api.binance.com")
        ).rstrip("/")
        self.session = session

    def get_ticker(self, symbol=None):
        response = self.session.get(
            f"{self.base_url}/api/v3/ticker/24hr",
            params={"symbol": str(symbol or SYMBOL).replace("/", "").upper()},
            timeout=10,
        )
        response.raise_for_status()
        ticker = response.json()
        if isinstance(ticker, dict) and int(ticker.get("code", 0)) < 0:
            raise RuntimeError(ticker.get("msg") or "Binance market API error")
        return {
            "price": float(ticker["lastPrice"]),
            "high": float(ticker["highPrice"]),
            "low": float(ticker["lowPrice"]),
            "volume": float(ticker["volume"]),
        }

    def get_klines(self, interval="240", limit=200, symbol=None):
        response = self.session.get(
            f"{self.base_url}/api/v3/klines",
            params={
                "symbol": str(symbol or SYMBOL).replace("/", "").upper(),
                "interval": normalize_binance_interval(interval),
                "limit": min(int(limit), 1000),
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and int(data.get("code", 0)) < 0:
            raise RuntimeError(data.get("msg") or "Binance market API error")
        frame = pd.DataFrame(
            [row[:7] for row in data],
            columns=["time", "open", "high", "low", "close", "volume", "turnover"],
        )
        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = frame[column].astype(float)
        return frame


__all__ = ["BinanceMarketDataProvider", "normalize_binance_interval"]
