import requests
import pandas as pd
from config import BYBIT_BASE_URL, SYMBOL


def get_ticker():
    """
    Получить текущую цену BTC.
    """

    url = f"{BYBIT_BASE_URL}/v5/market/tickers"

    params = {
        "category": "spot",
        "symbol": SYMBOL
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
   


def get_klines(interval="240", limit=200):
    """
    Получить свечи Bybit и вернуть DataFrame.
    interval:
        "240" = 4H
        "D"   = 1D
    """

    url = f"{BYBIT_BASE_URL}/v5/market/kline"

    params = {
        "category": "spot",
        "symbol": SYMBOL,
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