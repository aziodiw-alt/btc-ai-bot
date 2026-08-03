"""Pure entry-quality scoring for Swing and Fast profiles."""


def _distances(price, support, resistance, ema20):
    distance_to_resistance = (
        (resistance - price) / price * 100
        if resistance > price
        else 0.0
    )
    distance_to_ema20 = abs(price - ema20) / price * 100
    distance_from_support = (
        (price - support) / price * 100
        if price > support
        else 0.0
    )
    return distance_to_resistance, distance_to_ema20, distance_from_support


def score_swing_entry(price, support, resistance, ema20):
    distances = _distances(price, support, resistance, ema20)
    distance_to_resistance, distance_to_ema20, distance_from_support = distances
    score = 0
    reasons = []
    warnings = []

    if distance_to_resistance >= 2.0:
        score += 10
        reasons.append("До сопротивления есть запас минимум 2%")
    elif distance_to_resistance >= 1.5:
        score += 6
        warnings.append("До сопротивления запас только 1.5–2%")
    else:
        warnings.append("Цена слишком близко к сопротивлению")

    if distance_to_ema20 <= 1.2:
        score += 5
        reasons.append("Цена находится близко к EMA20")
    else:
        warnings.append("Цена далеко от EMA20")

    if distance_from_support <= 3.0:
        score += 5
        reasons.append("Цена относительно близко к поддержке")
    else:
        warnings.append("Цена далеко от поддержки")

    return score, distance_to_resistance, reasons, warnings


def score_fast_entry(price, support, resistance, ema20):
    distances = _distances(price, support, resistance, ema20)
    distance_to_resistance, distance_to_ema20, distance_from_support = distances
    score = 0
    reasons = []
    warnings = []

    if distance_to_resistance >= 1.2:
        score += 10
        reasons.append("Fast: до сопротивления есть запас минимум 1,2%")
    elif distance_to_resistance >= 0.8:
        score += 5
        warnings.append("Fast: запас до сопротивления ограничен")
    else:
        warnings.append("Fast: цена слишком близко к сопротивлению")

    if distance_to_ema20 <= 0.8:
        score += 7
        reasons.append("Fast 1H: цена рядом с EMA20")
    else:
        warnings.append("Fast 1H: цена далеко от EMA20")

    if distance_from_support <= 1.8:
        score += 8
        reasons.append("Fast: цена рядом с локальной поддержкой")
    else:
        warnings.append("Fast: цена далеко от локальной поддержки")

    return score, distance_to_resistance, reasons, warnings


__all__ = ["score_fast_entry", "score_swing_entry"]
