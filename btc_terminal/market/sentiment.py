"""Bybit derivatives sentiment provider used by all current strategies."""

import requests

from config import BYBIT_BASE_URL, SYMBOL


def _request(endpoint, params):
    response = requests.get(
        f"{BYBIT_BASE_URL}{endpoint}",
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("retCode") != 0:
        raise RuntimeError(data.get("retMsg", "Ошибка Bybit API"))

    return data["result"]["list"]


def get_funding(symbol=None):
    rows = _request(
        "/v5/market/funding/history",
        {
            "category": "linear",
            "symbol": symbol or SYMBOL,
            "limit": 2,
        },
    )
    if not rows:
        raise RuntimeError("Bybit не вернул данные Funding")
    return float(rows[0]["fundingRate"])


def get_open_interest(symbol=None):
    rows = _request(
        "/v5/market/open-interest",
        {
            "category": "linear",
            "symbol": symbol or SYMBOL,
            "intervalTime": "4h",
            "limit": 2,
        },
    )
    current = float(rows[0]["openInterest"])
    previous = float(rows[1]["openInterest"])
    change_pct = (
        (current - previous) / previous * 100
        if previous != 0
        else 0.0
    )
    return {
        "current": current,
        "previous": previous,
        "change_pct": change_pct,
    }


def get_long_short(symbol=None):
    rows = _request(
        "/v5/market/account-ratio",
        {
            "category": "linear",
            "symbol": symbol or SYMBOL,
            "period": "4h",
            "limit": 1,
        },
    )
    buy_ratio = float(rows[0]["buyRatio"])
    sell_ratio = float(rows[0]["sellRatio"])
    ratio = buy_ratio / sell_ratio if sell_ratio != 0 else 0.0
    return {
        "long_pct": buy_ratio * 100,
        "short_pct": sell_ratio * 100,
        "ratio": ratio,
    }


def get_sentiment(symbol=None):
    funding = get_funding(symbol)
    oi = get_open_interest(symbol)
    long_short = get_long_short(symbol)

    score = 0
    reasons = []
    warnings = []

    if abs(funding) <= 0.0003:
        score += 10
        reasons.append("Funding нейтральный")
    elif abs(funding) <= 0.0007:
        score += 6
        warnings.append("Funding умеренно повышен")
    else:
        warnings.append("Funding перегрет")

    ratio = long_short["ratio"]
    if 0.85 <= ratio <= 1.35:
        score += 10
        reasons.append("Long/Short без сильного перекоса")
    elif 0.70 <= ratio <= 1.70:
        score += 5
        warnings.append("Есть умеренный перекос Long/Short")
    else:
        warnings.append("Сильный перекос Long/Short")

    oi_change = oi["change_pct"]
    if 0 < oi_change <= 5:
        score += 10
        reasons.append("Open Interest умеренно растет")
    elif oi_change > 5:
        score += 5
        warnings.append("Open Interest растет слишком быстро")
    else:
        warnings.append("Open Interest не растет")

    return {
        "funding": funding,
        "funding_pct": funding * 100,
        "open_interest": oi["current"],
        "open_interest_change_pct": oi_change,
        "long_pct": long_short["long_pct"],
        "short_pct": long_short["short_pct"],
        "long_short_ratio": ratio,
        "sentiment_score": score,
        "reasons": reasons,
        "warnings": warnings,
    }


__all__ = [
    "get_funding",
    "get_long_short",
    "get_open_interest",
    "get_sentiment",
]
