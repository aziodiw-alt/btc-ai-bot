from sentiment import get_sentiment
from market import get_ticker, get_klines
from indicators import analyze


def calculate_support_resistance(df, lookback=50):
    recent = df.tail(lookback)

    support = float(recent["low"].min())
    resistance = float(recent["high"].max())

    return support, resistance


def analyze_strategy():
    ticker = get_ticker()
    price = float(ticker["price"])

    df_1d = get_klines("D", 250)
    df_4h = get_klines("240", 250)

    ind_1d = analyze(df_1d)
    ind_4h = analyze(df_4h)

    support, resistance = calculate_support_resistance(df_4h)

    trend_score = 0
    entry_score = 0
    indicators_score = 0
    reasons = []
    warnings = []

    # ==========================
    # 1. TREND: максимум 40
    # ==========================

    if price > ind_1d["ema200"]:
        trend_score += 15
        reasons.append("1D: цена выше EMA200")
    else:
        warnings.append("1D: цена ниже EMA200")

    if ind_1d["ema20"] > ind_1d["ema50"]:
        trend_score += 10
        reasons.append("1D: EMA20 выше EMA50")
    else:
        warnings.append("1D: EMA20 ниже EMA50")

    if price > ind_4h["ema200"]:
        trend_score += 10
        reasons.append("4H: цена выше EMA200")
    else:
        warnings.append("4H: цена ниже EMA200")

    if ind_4h["ema20"] > ind_4h["ema50"]:
        trend_score += 5
        reasons.append("4H: EMA20 выше EMA50")
    else:
        warnings.append("4H: EMA20 ниже EMA50")

    # ==========================
    # 2. ENTRY QUALITY: максимум 20
    # ==========================

    distance_to_resistance = (
        (resistance - price) / price * 100
        if resistance > price
        else 0.0
    )

    distance_to_ema20 = abs(
        price - ind_4h["ema20"]
    ) / price * 100

    distance_from_support = (
        (price - support) / price * 100
        if price > support
        else 0.0
    )

    if distance_to_resistance >= 2.0:
        entry_score += 10
        reasons.append("До сопротивления есть запас минимум 2%")
    elif distance_to_resistance >= 1.5:
        entry_score += 6
        warnings.append("До сопротивления запас только 1.5–2%")
    else:
        warnings.append("Цена слишком близко к сопротивлению")

    if distance_to_ema20 <= 1.2:
        entry_score += 5
        reasons.append("Цена находится близко к EMA20")
    else:
        warnings.append("Цена далеко от EMA20")

    if distance_from_support <= 3.0:
        entry_score += 5
        reasons.append("Цена относительно близко к поддержке")
    else:
        warnings.append("Цена далеко от поддержки")

    # ==========================
    # 3. INDICATORS: максимум 10
    # ==========================

    if 45 <= ind_4h["rsi"] <= 62:
        indicators_score += 5
        reasons.append("RSI 4H находится в рабочей зоне")
    elif ind_4h["rsi"] > 70:
        warnings.append("RSI 4H показывает перегрев")
    else:
        warnings.append("RSI 4H вне оптимальной зоны")

    if ind_4h["macd"] > ind_4h["macd_signal"]:
        indicators_score += 5
        reasons.append("MACD 4H бычий")
    else:
        warnings.append("MACD 4H пока слабый")

    # ==========================
    # 4. SENTIMENT: максимум 30
    # ==========================

    sentiment = get_sentiment()
    sentiment_score = sentiment["sentiment_score"]

    reasons.extend(sentiment["reasons"])
    warnings.extend(sentiment["warnings"])

    total_score = (
        trend_score
        + entry_score
        + indicators_score
        + sentiment_score
    )

    # Обязательный фильтр: при слабом тренде сигнал блокируется
    if trend_score < 20:
        grade = "SKIP"
        decision = "SKIP — слабый дневной тренд"
        warnings.append("Главный фильтр: тренд слишком слабый")

    elif total_score >= 85:
        grade = "A+"
        decision = "BUY LIMIT — хороший сигнал"

    elif total_score >= 75:
        grade = "A"
        decision = "WAIT / BUY LIMIT на откате"

    elif total_score >= 65:
        grade = "B"
        decision = "WAIT — условия средние"

    elif total_score >= 50:
        grade = "C"
        decision = "SKIP — слабый вход"

    else:
        grade = "SKIP"
        decision = "SKIP — вход не рекомендуется"


    # ==========================
    # 5. TRADE LEVELS
    # ==========================

    buy_zone_1_high = round(price * 0.995, 2)
    buy_zone_1_low = round(price * 0.991, 2)

    buy_zone_2_high = round(price * 0.987, 2)
    buy_zone_2_low = round(price * 0.982, 2)

    stop_loss = round(support * 0.995, 2)

    # Для стратегии небольших спотовых сделок считаем прибыль
    # от верхней границы первой лимитной зоны. Это консервативнее:
    # фактическая покупка ниже даст немного лучший результат.
    planned_entry = buy_zone_1_high
    safe_resistance = round(resistance * 0.995, 2)
    available_profit_pct = (
        (safe_resistance - planned_entry) / planned_entry * 100
        if safe_resistance > planned_entry
        else 0.0
    )
    target_15_20_available = available_profit_pct >= 1.5

    take_profit_1 = round(
        min(planned_entry * 1.015, safe_resistance),
        2,
    )
    take_profit_2 = round(
        min(planned_entry * 1.020, safe_resistance),
        2,
    )

    if grade in {"A", "A+"} and not target_15_20_available:
        grade = "B"
        decision = "WAIT — до безопасной цели нет запаса 1.5%"
        warnings.append(
            "Автосигнал заблокирован: потенциал до сопротивления меньше 1.5%"
        )
    elif grade in {"A", "A+"}:
        decision = "BUY LIMIT — доступна цель примерно 1.5–2%"

    return {
        "price": round(price, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "distance_to_resistance_pct": round(
            distance_to_resistance, 2
        ),
        "trend_score": trend_score,
        "entry_score": entry_score,
        "indicators_score": indicators_score,
        "sentiment_score": sentiment_score,
        "total_score": total_score,
        "score_max": 100,
        "grade": grade,
        "decision": decision,
        "rsi_4h": round(ind_4h["rsi"], 2),
        "funding_pct": round(sentiment["funding_pct"], 5),
        "long_short_ratio": round(
            sentiment["long_short_ratio"], 3
        ),
        "open_interest_change_pct": round(
            sentiment["open_interest_change_pct"], 2
        ),
        "reasons": reasons,
        "warnings": warnings,
        "buy_zone_1": [buy_zone_1_low, buy_zone_1_high],
        "buy_zone_2": [buy_zone_2_low, buy_zone_2_high],
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "planned_entry": planned_entry,
        "available_profit_pct": round(available_profit_pct, 2),
        "target_15_20_available": target_15_20_available,
    }
