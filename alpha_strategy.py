"""Conservative Alpha strategy derived from the formal rules in the guide."""

def _avoid_round_number(price, symbol):
    """Move a planned order slightly below crowded round-number prices."""
    price = float(price)
    if symbol == "BTCUSDT":
        step, buffer_size, threshold = 100.0, 17.0, 22.0
    else:
        step, buffer_size, threshold = 10.0, 1.7, 2.2

    nearest = round(price / step) * step
    if abs(price - nearest) <= threshold:
        price = nearest - buffer_size
    return round(price, 2)


def _ordered_zone(low, high, symbol):
    values = sorted(
        (_avoid_round_number(low, symbol), _avoid_round_number(high, symbol))
    )
    if values[0] == values[1]:
        values[0] = round(values[0] - (5 if symbol == "BTCUSDT" else 0.5), 2)
    return values


def calculate_alpha_levels(price, support, resistance, atr, symbol):
    """Create pullback entries, profit targets, and a profit-only trail plan."""
    price = float(price)
    support = float(support)
    resistance = float(resistance)
    atr = max(float(atr), price * 0.002)

    zone_1_center = min(price - 0.35 * atr, max(support + 0.45 * atr, price - 0.80 * atr))
    zone_2_center = min(zone_1_center - 0.35 * atr, max(support + 0.12 * atr, price - 1.45 * atr))

    buy_zone_1 = _ordered_zone(
        zone_1_center - 0.12 * atr,
        zone_1_center + 0.12 * atr,
        symbol,
    )
    buy_zone_2 = _ordered_zone(
        zone_2_center - 0.12 * atr,
        zone_2_center + 0.12 * atr,
        symbol,
    )

    entries = [
        {"label": "Entry 1", "allocation_pct": 20, "price": buy_zone_1[1]},
        {"label": "Entry 2", "allocation_pct": 30, "price": buy_zone_1[0]},
        {
            "label": "Entry 3",
            "allocation_pct": 50,
            "price": round(sum(buy_zone_2) / 2, 2),
        },
    ]
    planned_entry = round(
        sum(item["price"] * item["allocation_pct"] for item in entries) / 100,
        2,
    )

    safe_resistance = resistance * 0.995
    take_profit_1 = _avoid_round_number(
        min(planned_entry * 1.015, safe_resistance),
        symbol,
    )
    take_profit_2 = _avoid_round_number(
        min(planned_entry * 1.020, safe_resistance),
        symbol,
    )
    stop_loss = _avoid_round_number(
        min(support - 0.25 * atr, planned_entry - 1.10 * atr),
        symbol,
    )

    trail_distance_pct = round(
        max(0.45, min(0.90, atr / planned_entry * 100 * 0.75)),
        2,
    )
    protected_stop = _avoid_round_number(planned_entry * 1.003, symbol)
    available_profit_pct = max(
        0.0,
        (safe_resistance - planned_entry) / planned_entry * 100,
    )

    return {
        "buy_zone_1": buy_zone_1,
        "buy_zone_2": buy_zone_2,
        "entry_plan": entries,
        "planned_entry": planned_entry,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "available_profit_pct": round(available_profit_pct, 2),
        "target_available": available_profit_pct >= 1.5,
        "trailing_stop": {
            "enabled_after_profit": True,
            "activation_price": take_profit_1,
            "activation_profit_pct": 1.5,
            "protected_stop": protected_stop,
            "trail_distance_pct": trail_distance_pct,
            "rule": "После TP1 перенести защиту выше средней цены входа и сопровождать рост.",
        },
    }


def analyze_alpha_strategy(symbol="BTCUSDT"):
    """Return an optional conservative Alpha analysis without changing other modes."""
    from indicators import analyze
    from levels import calculate_support_resistance
    from market import get_klines, get_ticker
    from sentiment import get_sentiment

    price = float(get_ticker(symbol)["price"])
    frame_1d = get_klines("D", 250, symbol)
    frame_4h = get_klines("240", 250, symbol)
    ind_1d = analyze(frame_1d)
    ind_4h = analyze(frame_4h)
    support, resistance = calculate_support_resistance(frame_4h, lookback=80)
    sentiment = get_sentiment(symbol)
    levels = calculate_alpha_levels(
        price,
        support,
        resistance,
        ind_4h["atr"],
        symbol,
    )

    reasons = []
    warnings = []
    trend_score = 0
    entry_score = 0
    indicators_score = 0

    if price > ind_1d["ema200"]:
        trend_score += 15
        reasons.append("Alpha 1D: цена выше EMA200")
    else:
        warnings.append("Alpha 1D: цена ниже EMA200")
    if ind_1d["ema20"] > ind_1d["ema50"]:
        trend_score += 10
        reasons.append("Alpha 1D: EMA20 выше EMA50")
    else:
        warnings.append("Alpha 1D: среднесрочный тренд не подтвержден")
    if price > ind_4h["ema200"]:
        trend_score += 10
        reasons.append("Alpha 4H: цена выше EMA200")
    else:
        warnings.append("Alpha 4H: цена ниже EMA200")
    if ind_4h["ema20"] > ind_4h["ema50"]:
        trend_score += 5
        reasons.append("Alpha 4H: EMA20 выше EMA50")
    else:
        warnings.append("Alpha 4H: EMA20 ниже EMA50")

    three_candle_return = (
        (float(frame_4h.iloc[-1]["close"]) / float(frame_4h.iloc[-4]["close"]) - 1)
        * 100
    )
    distance_above_ema_atr = (price - ind_4h["ema20"]) / max(ind_4h["atr"], 1)
    sharp_upward_momentum = (
        three_candle_return >= 2.5
        or distance_above_ema_atr >= 1.25
        or ind_4h["rsi"] >= 68
    )

    if sharp_upward_momentum:
        warnings.append(
            "Alpha-фильтр: резкий рост уже идет; не покупать вслед за импульсом"
        )
    else:
        entry_score += 10
        reasons.append("Нет резкого восходящего импульса")

    pullback_pct = (price - levels["planned_entry"]) / price * 100
    if 0.4 <= pullback_pct <= 3.5:
        entry_score += 5
        reasons.append("План входа расположен на контролируемом откате")
    else:
        warnings.append("Планируемый откат находится вне комфортного диапазона Alpha")
    if levels["target_available"]:
        entry_score += 5
        reasons.append("До безопасной цели есть запас не менее 1,5%")
    else:
        warnings.append("До сопротивления недостаточно места для цели 1,5%")

    rsi_score = 0
    macd_score = 0
    if 42 <= ind_4h["rsi"] <= 62:
        rsi_score = 5
        reasons.append("RSI 4H находится в спокойной рабочей зоне")
    else:
        warnings.append("RSI 4H вне консервативной зоны Alpha")
    if ind_4h["macd"] > ind_4h["macd_signal"]:
        macd_score = 5
        reasons.append("MACD 4H подтверждает покупателей")
    else:
        warnings.append("MACD 4H пока не подтверждает вход")
    indicators_score = rsi_score + macd_score

    sentiment_score = min(max(int(sentiment["sentiment_score"]), 0), 30)
    reasons.extend(sentiment["reasons"])
    warnings.extend(sentiment["warnings"])
    total_score = trend_score + entry_score + indicators_score + sentiment_score

    hard_block = (
        sharp_upward_momentum
        or trend_score < 25
        or not levels["target_available"]
    )
    if hard_block:
        grade = "SKIP"
        decision = "ALPHA WAIT - вход только после спокойного отката"
    elif total_score >= 85:
        grade = "A+"
        decision = "ALPHA BUY LIMIT - использовать входы 20% / 30% / 50%"
    elif total_score >= 75:
        grade = "A"
        decision = "ALPHA WAIT / BUY LIMIT - дождаться первой зоны"
    elif total_score >= 65:
        grade = "B"
        decision = "ALPHA WAIT - условия пока средние"
    else:
        grade = "SKIP"
        decision = "ALPHA SKIP - консервативного преимущества нет"

    return {
        "symbol": symbol,
        "display_symbol": symbol.replace("USDT", "/USDT"),
        "asset": symbol.replace("USDT", ""),
        "strategy_key": "alpha",
        "strategy_name": "Alpha",
        "strategy_description": "Консервативный откат · 1D + 4H · входы 20/30/50",
        "price": round(price, 2),
        "current_price": round(price, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "distance_to_resistance_pct": round(
            max(0.0, (resistance - price) / price * 100),
            2,
        ),
        "trend_score": trend_score,
        "trend_max": 40,
        "entry_score": entry_score,
        "entry_max": 20,
        "indicators_score": indicators_score,
        "indicators_max": 10,
        "rsi_score": rsi_score,
        "rsi_max": 5,
        "macd_score": macd_score,
        "macd_max": 5,
        "sentiment_score": sentiment_score,
        "sentiment_max": 30,
        "total_score": total_score,
        "score_max": 100,
        "grade": grade,
        "decision": decision,
        "rsi_4h": round(ind_4h["rsi"], 2),
        "rsi_label": "RSI 4H",
        "funding_pct": round(sentiment["funding_pct"], 5),
        "long_short_ratio": round(sentiment["long_short_ratio"], 3),
        "open_interest_change_pct": round(
            sentiment["open_interest_change_pct"],
            2,
        ),
        "reasons": reasons,
        "warnings": warnings,
        "buy_zone_1": levels["buy_zone_1"],
        "buy_zone_2": levels["buy_zone_2"],
        "entry_plan": levels["entry_plan"],
        "planned_entry": levels["planned_entry"],
        "stop_loss": levels["stop_loss"],
        "take_profit_1": levels["take_profit_1"],
        "take_profit_2": levels["take_profit_2"],
        "available_profit_pct": levels["available_profit_pct"],
        "target_15_20_available": levels["target_available"],
        "sharp_upward_momentum": sharp_upward_momentum,
        "momentum_3_candle_pct": round(three_candle_return, 2),
        "trailing_stop": levels["trailing_stop"],
        "entry_status": (
            "WAIT_PULLBACK"
            if price > levels["buy_zone_1"][1]
            else "IN_ENTRY_ZONE"
            if price >= levels["buy_zone_2"][0]
            else "RECALCULATE"
        ),
    }
