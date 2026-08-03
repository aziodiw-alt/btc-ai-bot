"""Classify the market before applying entry and grading rules."""


def detect_market_state(price, indicators_1d, indicators_4h):
    price = float(price)

    daily_bullish = (
        price > indicators_1d["ema200"]
        and indicators_1d["ema20"] > indicators_1d["ema50"]
    )
    daily_bearish = (
        price < indicators_1d["ema200"]
        and indicators_1d["ema20"] < indicators_1d["ema50"]
    )
    four_hour_bullish = (
        price > indicators_4h["ema200"]
        and indicators_4h["ema20"] > indicators_4h["ema50"]
    )
    four_hour_bearish = (
        price < indicators_4h["ema200"]
        and indicators_4h["ema20"] < indicators_4h["ema50"]
    )

    if daily_bullish and four_hour_bullish:
        return {
            "key": "UPTREND",
            "label": "Восходящий тренд",
            "description": "Покупаем откаты по направлению основного тренда.",
        }

    if daily_bearish and four_hour_bearish:
        return {
            "key": "DOWNTREND",
            "label": "Нисходящий тренд",
            "description": "Для спота новые покупки блокируются.",
        }

    return {
        "key": "RANGE",
        "label": "Диапазон",
        "description": "Покупаем возле поддержки и фиксируем прибыль до сопротивления.",
    }


__all__ = ["detect_market_state"]
