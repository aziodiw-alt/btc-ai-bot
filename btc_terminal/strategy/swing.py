from btc_terminal.market.sentiment import get_sentiment
from market import get_ticker, get_klines
from btc_terminal.strategy.indicators import analyze
from btc_terminal.strategy.levels import (
    calculate_support_resistance,
    calculate_trade_levels,
)
from btc_terminal.strategy.market_state import detect_market_state
from btc_terminal.strategy.grading import grade_swing
from btc_terminal.strategy.risk import apply_swing_safety_filters
from btc_terminal.strategy.trend import score_swing_trend
from btc_terminal.strategy.entry import score_swing_entry
from btc_terminal.strategy.momentum import score_swing_momentum


def analyze_strategy(symbol="BTCUSDT", exchange="bybit"):
    ticker = get_ticker(symbol, exchange=exchange)
    price = float(ticker["price"])

    df_1d = get_klines("D", 250, symbol, exchange=exchange)
    df_4h = get_klines("240", 250, symbol, exchange=exchange)

    ind_1d = analyze(df_1d)
    ind_4h = analyze(df_4h)
    market_state = detect_market_state(price, ind_1d, ind_4h)

    support, resistance = calculate_support_resistance(df_4h)

    trend_score, reasons, warnings = score_swing_trend(
        price,
        ind_1d,
        ind_4h,
    )
    entry_score, distance_to_resistance, entry_reasons, entry_warnings = (
        score_swing_entry(price, support, resistance, ind_4h["ema20"])
    )
    reasons.extend(entry_reasons)
    warnings.extend(entry_warnings)
    rsi_score, macd_score, momentum_reasons, momentum_warnings = (
        score_swing_momentum(ind_4h)
    )
    indicators_score = rsi_score + macd_score
    reasons.extend(momentum_reasons)
    warnings.extend(momentum_warnings)
    sentiment = get_sentiment(symbol)
    sentiment_score = sentiment["sentiment_score"]

    reasons.extend(sentiment["reasons"])
    warnings.extend(sentiment["warnings"])

    total_score = (
        trend_score
        + entry_score
        + indicators_score
        + sentiment_score
    )

    grade, decision = grade_swing(total_score, market_state["key"])

    if market_state["key"] == "DOWNTREND":
        warnings.append("Режим DOWNTREND: новые спотовые покупки заблокированы")


    # ==========================
    # 5. TRADE LEVELS
    # ==========================

    trade_levels = calculate_trade_levels(
        price,
        support,
        resistance,
        atr=ind_4h["atr"],
        profile="swing",
    )
    target_15_20_available = trade_levels["target_available"]

    grade, decision, safety_warning = apply_swing_safety_filters(
        grade,
        decision,
        market_state_key=market_state["key"],
        entry_score=entry_score,
        target_available=target_15_20_available,
    )
    if safety_warning:
        warnings.append(safety_warning)

    return {
        "symbol": symbol,
        "exchange": exchange,
        "display_symbol": (
            symbol.replace("USDT", "/USD (USDC)")
            if exchange == "okx"
            else symbol.replace("USDT", "/USDT")
        ),
        "asset": symbol.replace("USDT", ""),
        "strategy_key": "swing",
        "strategy_name": "Swing",
        "market_mode": market_state["key"],
        "market_mode_label": market_state["label"],
        "market_mode_description": market_state["description"],
        "price": round(price, 2),
        "support": round(support, 2),
        "support_zone": trade_levels["support_zone"],
        "resistance": round(resistance, 2),
        "distance_to_resistance_pct": round(
            distance_to_resistance, 2
        ),
        "trend_score": trend_score,
        "entry_score": entry_score,
        "indicators_score": indicators_score,
        "rsi_score": rsi_score,
        "macd_score": macd_score,
        "sentiment_score": sentiment_score,
        "total_score": total_score,
        "score_max": 100,
        "grade": grade,
        "decision": decision,
        "rsi_4h": round(ind_4h["rsi"], 2),
        "macd_4h": round(ind_4h["macd"], 2),
        "macd_signal_4h": round(ind_4h["macd_signal"], 2),
        "funding_pct": round(sentiment["funding_pct"], 5),
        "long_short_ratio": round(
            sentiment["long_short_ratio"], 3
        ),
        "open_interest_change_pct": round(
            sentiment["open_interest_change_pct"], 2
        ),
        "reasons": reasons,
        "warnings": warnings,
        "buy_zone_1": trade_levels["buy_zone_1"],
        "buy_zone_2": trade_levels["buy_zone_2"],
        "stop_loss": trade_levels["stop_loss"],
        "take_profit_1": trade_levels["take_profit_1"],
        "take_profit_2": trade_levels["take_profit_2"],
        "planned_entry": trade_levels["planned_entry"],
        "available_profit_pct": trade_levels["available_profit_pct"],
        "target_15_20_available": target_15_20_available,
    }
