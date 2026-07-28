import os

import requests
import pandas as pd
from config import BYBIT_BASE_URL, SYMBOL


def _normalize_exchange(exchange):
    return "okx" if str(exchange).lower() == "okx" else "bybit"


def _okx_symbol(symbol):
    normalized = str(symbol or SYMBOL).replace("/", "").replace("-", "").upper()
    if normalized.endswith("USDT"):
        return normalized[:-4] + "-USDC"
    if normalized.endswith("USDC"):
        return normalized[:-4] + "-USDC"
    return normalized


def _okx_interval(interval):
    return {
        "60": "1H",
        "240": "4H",
        "D": "1Dutc",
    }.get(str(interval), str(interval))


def get_ticker(symbol=None, exchange="bybit"):
    """
    Получить текущую цену BTC.
    """

    if _normalize_exchange(exchange) == "okx":
        base_url = os.getenv("OKX_API_BASE", "https://eea.okx.com").rstrip("/")
        response = requests.get(
            f"{base_url}/api/v5/market/ticker",
            params={"instId": _okx_symbol(symbol)},
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

    url = f"{BYBIT_BASE_URL}/v5/market/tickers"

    params = {
        "category": "spot",
        "symbol": symbol or SYMBOL
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if data["retCode"] != 0:
        raise Exception(data["retMsg"])

    ticker = data["result"]["list"][0]

    return {
        "price": float(ticker["lastPrice"]),
        "high": float(ticker["highPrice24h"]),
        "low": float(ticker["lowPrice24h"]),
        "volume": float(ticker["volume24h"])
    }
   


def get_klines(interval="240", limit=200, symbol=None, exchange="bybit"):
    """
    Получить свечи Bybit и вернуть DataFrame.
    interval:
        "240" = 4H
        "D"   = 1D
    """

    if _normalize_exchange(exchange) == "okx":
        base_url = os.getenv("OKX_API_BASE", "https://eea.okx.com").rstrip("/")
        response = requests.get(
            f"{base_url}/api/v5/market/candles",
            params={
                "instId": _okx_symbol(symbol),
                "bar": _okx_interval(interval),
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

    url = f"{BYBIT_BASE_URL}/v5/market/kline"

    params = {
        "category": "spot",
        "symbol": symbol or SYMBOL,
        "interval": interval,
        "limit": limit
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if data["retCode"] != 0:
        raise Exception(data["retMsg"])

    rows = data["result"]["list"]

    rows.reverse()

    df = pd.DataFrame(rows, columns=[
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover"
    ])

    numeric = ["open", "high", "low", "close", "volume"]

    for col in numeric:
        df[col] = df[col].astype(float)

    return df
