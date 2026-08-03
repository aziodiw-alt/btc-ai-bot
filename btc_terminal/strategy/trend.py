"""Pure EMA-based trend scoring for Swing and Fast profiles."""


def score_swing_trend(price, indicators_1d, indicators_4h):
    score = 0
    reasons = []
    warnings = []

    if price > indicators_1d["ema200"]:
        score += 15
        reasons.append("1D: цена выше EMA200")
    else:
        warnings.append("1D: цена ниже EMA200")

    if indicators_1d["ema20"] > indicators_1d["ema50"]:
        score += 10
        reasons.append("1D: EMA20 выше EMA50")
    else:
        warnings.append("1D: EMA20 ниже EMA50")

    if price > indicators_4h["ema200"]:
        score += 10
        reasons.append("4H: цена выше EMA200")
    else:
        warnings.append("4H: цена ниже EMA200")

    if indicators_4h["ema20"] > indicators_4h["ema50"]:
        score += 5
        reasons.append("4H: EMA20 выше EMA50")
    else:
        warnings.append("4H: EMA20 ниже EMA50")

    return score, reasons, warnings


def score_fast_trend(price, indicators_4h, indicators_1h):
    score = 0
    reasons = []
    warnings = []

    if price > indicators_4h["ema200"]:
        score += 15
        reasons.append("Fast 4H: цена выше EMA200")
    else:
        warnings.append("Fast 4H: цена ниже EMA200")

    if indicators_4h["ema20"] > indicators_4h["ema50"]:
        score += 10
        reasons.append("Fast 4H: EMA20 выше EMA50")
    else:
        warnings.append("Fast 4H: EMA20 ниже EMA50")

    if price > indicators_1h["ema200"]:
        score += 5
        reasons.append("Fast 1H: цена выше EMA200")
    else:
        warnings.append("Fast 1H: цена ниже EMA200")

    if indicators_1h["ema20"] > indicators_1h["ema50"]:
        score += 5
        reasons.append("Fast 1H: EMA20 выше EMA50")
    else:
        warnings.append("Fast 1H: EMA20 ниже EMA50")

    return score, reasons, warnings


__all__ = ["score_fast_trend", "score_swing_trend"]
