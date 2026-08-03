"""Pure RSI and MACD scoring for current strategy profiles."""


def score_swing_momentum(indicators_4h):
    rsi_score = 0
    macd_score = 0
    reasons = []
    warnings = []
    rsi = indicators_4h["rsi"]

    if 45 <= rsi <= 62:
        rsi_score = 5
        reasons.append("RSI 4H находится в основной рабочей зоне")
    elif 40 <= rsi < 45:
        rsi_score = 3
        reasons.append("RSI 4H восстанавливается из слабой зоны")
    elif 30 <= rsi < 40:
        rsi_score = 2
        warnings.append("RSI 4H слабый, но рынок уже близок к перепроданности")
    elif 62 < rsi <= 68:
        rsi_score = 3
        warnings.append("RSI 4H повышенный, но перегрева пока нет")
    elif rsi < 30:
        rsi_score = 1
        warnings.append("RSI 4H показывает перепроданность и высокий риск")
    else:
        warnings.append("RSI 4H показывает перегрев")

    if indicators_4h["macd"] > indicators_4h["macd_signal"]:
        macd_score = 5
        reasons.append("MACD 4H бычий")
    elif (
        indicators_4h["macd_histogram"]
        > indicators_4h["macd_histogram_previous"]
    ):
        macd_score = 2
        reasons.append("MACD 4H ещё слабый, но импульс улучшается")
    else:
        warnings.append("MACD 4H слабый и пока не улучшается")

    return rsi_score, macd_score, reasons, warnings


def score_fast_momentum(indicators_1h):
    rsi_score = 0
    macd_score = 0
    reasons = []
    warnings = []
    rsi = indicators_1h["rsi"]

    if 42 <= rsi <= 60:
        rsi_score = 10
        reasons.append("Fast RSI 1H в рабочей зоне")
    elif 36 <= rsi < 42 or 60 < rsi <= 66:
        rsi_score = 6
        warnings.append("Fast RSI 1H допустимый, но не идеальный")
    elif 30 <= rsi < 36:
        rsi_score = 3
        warnings.append("Fast RSI 1H слабый")
    elif rsi < 30:
        rsi_score = 2
        warnings.append(
            "Fast RSI 1H показывает перепроданность, "
            "но требуется подтверждение разворота"
        )
    else:
        warnings.append("Fast RSI 1H вне рабочей зоны")

    histogram = indicators_1h.get(
        "macd_histogram",
        indicators_1h["macd"] - indicators_1h["macd_signal"],
    )
    histogram_previous = indicators_1h.get(
        "macd_histogram_previous",
        histogram,
    )

    if indicators_1h["macd"] > indicators_1h["macd_signal"]:
        macd_score = 10
        reasons.append("Fast MACD 1H бычий")
    elif histogram > histogram_previous:
        macd_score = 5
        reasons.append("Fast MACD 1H улучшается")
    else:
        warnings.append("Fast MACD 1H слабый")

    return rsi_score, macd_score, reasons, warnings


__all__ = ["score_fast_momentum", "score_swing_momentum"]
