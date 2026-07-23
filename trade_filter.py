from config import *


def evaluate(indicators, price):
    score = 0
    reasons = []

    # EMA200
    if price > indicators["ema200"]:
        score += SCORE_EMA200
        reasons.append("Цена выше EMA200")

    # EMA20 > EMA50
    if indicators["ema20"] > indicators["ema50"]:
        score += SCORE_EMA20
        reasons.append("EMA20 выше EMA50")

    # RSI
    if RSI_MIN <= indicators["rsi"] <= RSI_MAX:
        score += SCORE_RSI
        reasons.append("RSI в хорошей зоне")

    # MACD
    if indicators["macd"] > indicators["macd_signal"]:
        score += SCORE_MACD
        reasons.append("MACD бычий")

    # Оценка
    if score >= GRADE_A_PLUS:
        grade = "A+"

    elif score >= GRADE_A:
        grade = "A"

    elif score >= GRADE_B:
        grade = "B"

    elif score >= GRADE_C:
        grade = "C"

    else:
        grade = "SKIP"

    return {
        "score": score,
        "grade": grade,
        "reasons": reasons
    }