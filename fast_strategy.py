from indicators import analyze
from market import get_klines, get_ticker
from sentiment import get_sentiment
from levels import calculate_support_resistance, calculate_trade_levels


def analyze_fast_strategy(symbol="BTCUSDT"):
    price = float(get_ticker(symbol)["price"])
    frame_4h = get_klines("240", 250, symbol)
    frame_1h = get_klines("60", 250, symbol)
    ind_4h = analyze(frame_4h)
    ind_1h = analyze(frame_1h)
    support, resistance = calculate_support_resistance(frame_1h, lookback=80)

    trend_score = 0
    entry_score = 0
    rsi_score = 0
    macd_score = 0
    reasons = []
    warnings = []

    if price > ind_4h["ema200"]:
        trend_score += 15
        reasons.append("Fast 4H: цена выше EMA200")
    else:
        warnings.append("Fast 4H: цена ниже EMA200")

    if ind_4h["ema20"] > ind_4h["ema50"]:
        trend_score += 10
        reasons.append("Fast 4H: EMA20 выше EMA50")
    else:
        warnings.append("Fast 4H: EMA20 ниже EMA50")

    if price > ind_1h["ema200"]:
        trend_score += 5
        reasons.append("Fast 1H: цена выше EMA200")
    else:
        warnings.append("Fast 1H: цена ниже EMA200")

    if ind_1h["ema20"] > ind_1h["ema50"]:
        trend_score += 5
        reasons.append("Fast 1H: EMA20 выше EMA50")
    else:
        warnings.append("Fast 1H: EMA20 ниже EMA50")

    distance_to_resistance = (
        (resistance - price) / price * 100
        if resistance > price
        else 0.0
    )
    distance_to_ema20 = abs(price - ind_1h["ema20"]) / price * 100
    distance_from_support = (
        (price - support) / price * 100
        if price > support
        else 0.0
    )

    if distance_to_resistance >= 1.2:
        entry_score += 10
        reasons.append("Fast: до сопротивления есть запас минимум 1,2%")
    elif distance_to_resistance >= 0.8:
        entry_score += 5
        warnings.append("Fast: запас до сопротивления ограничен")
    else:
        warnings.append("Fast: цена слишком близко к сопротивлению")

    if distance_to_ema20 <= 0.8:
        entry_score += 7
        reasons.append("Fast 1H: цена рядом с EMA20")
    else:
        warnings.append("Fast 1H: цена далеко от EMA20")

    if distance_from_support <= 1.8:
        entry_score += 8
        reasons.append("Fast: цена рядом с локальной поддержкой")
    else:
        warnings.append("Fast: цена далеко от локальной поддержки")

    rsi = ind_1h["rsi"]
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

    histogram = ind_1h.get(
        "macd_histogram",
        ind_1h["macd"] - ind_1h["macd_signal"],
    )
    histogram_previous = ind_1h.get(
        "macd_histogram_previous",
        histogram,
    )

    if ind_1h["macd"] > ind_1h["macd_signal"]:
        macd_score = 10
        reasons.append("Fast MACD 1H бычий")
    elif histogram > histogram_previous:
        macd_score = 5
        reasons.append("Fast MACD 1H улучшается")
    else:
        warnings.append("Fast MACD 1H слабый")

    indicators_score = rsi_score + macd_score
    sentiment = get_sentiment(symbol)
    sentiment_score = round(
        min(max(sentiment["sentiment_score"], 0), 30) * 20 / 30
    )
    reasons.extend(sentiment["reasons"])
    warnings.extend(sentiment["warnings"])

    total_score = (
        trend_score
        + entry_score
        + indicators_score
        + sentiment_score
    )

    if trend_score < 20:
        grade = "SKIP"
        decision = "FAST SKIP — направление 4H слишком слабое"
    elif total_score >= 85:
        grade = "A+"
        decision = "FAST BUY LIMIT — сильный короткий сигнал"
    elif total_score >= 75:
        grade = "A"
        decision = "FAST BUY LIMIT — допустим небольшой объём"
    elif total_score >= 65:
        grade = "B"
        decision = "FAST WAIT — ждать более точного входа"
    else:
        grade = "SKIP"
        decision = "FAST SKIP — преимущества недостаточно"

    trade_levels = calculate_trade_levels(
        price,
        support,
        resistance,
        profile="fast",
    )
    available_profit_pct = trade_levels["available_profit_pct"]

    if grade in {"A", "A+"} and available_profit_pct < 0.8:
        grade = "B"
        decision = "FAST WAIT — до цели нет запаса 0,8%"
        warnings.append("Fast-сигнал заблокирован близким сопротивлением")

    return {
        "symbol": symbol,
        "display_symbol": symbol.replace("USDT", "/USDT"),
        "asset": symbol.replace("USDT", ""),
        "strategy_key": "fast",
        "strategy_name": "Fast",
        "strategy_description": "Частые небольшие сделки · 4H + 1H",
        "price": round(price, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "distance_to_resistance_pct": round(distance_to_resistance, 2),
        "trend_score": trend_score,
        "trend_max": 35,
        "entry_score": entry_score,
        "entry_max": 25,
        "indicators_score": indicators_score,
        "indicators_max": 20,
        "rsi_score": rsi_score,
        "rsi_max": 10,
        "macd_score": macd_score,
        "macd_max": 10,
        "sentiment_score": sentiment_score,
        "sentiment_max": 20,
        "total_score": total_score,
        "score_max": 100,
        "grade": grade,
        "decision": decision,
        "rsi_4h": round(rsi, 2),
        "rsi_label": "RSI 1H",
        "funding_pct": round(sentiment["funding_pct"], 5),
        "long_short_ratio": round(sentiment["long_short_ratio"], 3),
        "open_interest_change_pct": round(
            sentiment["open_interest_change_pct"],
            2,
        ),
        "reasons": reasons,
        "warnings": warnings,
        "buy_zone_1": trade_levels["buy_zone_1"],
        "buy_zone_2": trade_levels["buy_zone_2"],
        "stop_loss": trade_levels["stop_loss"],
        "take_profit_1": trade_levels["take_profit_1"],
        "take_profit_2": trade_levels["take_profit_2"],
        "planned_entry": trade_levels["planned_entry"],
        "available_profit_pct": round(available_profit_pct, 2),
        "target_15_20_available": available_profit_pct >= 0.8,
    }
