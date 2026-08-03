
from btc_terminal.strategy.indicators import analyze
from market import get_klines, get_ticker
from btc_terminal.market.sentiment import get_sentiment
from btc_terminal.strategy.levels import (
    calculate_support_resistance,
    calculate_trade_levels,
)
from btc_terminal.strategy.market_state import detect_market_state
from btc_terminal.strategy.grading import grade_fast
from btc_terminal.strategy.risk import apply_fast_safety_filters
from btc_terminal.strategy.trend import score_fast_trend
from btc_terminal.strategy.entry import score_fast_entry
from btc_terminal.strategy.momentum import score_fast_momentum


def analyze_fast_strategy(symbol="BTCUSDT", exchange="bybit"):
    price = float(get_ticker(symbol, exchange=exchange)["price"])
    frame_4h = get_klines("240", 250, symbol, exchange=exchange)
    frame_1h = get_klines("60", 250, symbol, exchange=exchange)
    ind_4h = analyze(frame_4h)
    ind_1h = analyze(frame_1h)
    market_state = detect_market_state(price, ind_4h, ind_1h)
    support, resistance = calculate_support_resistance(frame_1h, lookback=80)

    trend_score, reasons, warnings = score_fast_trend(
        price,
        ind_4h,
        ind_1h,
    )
    entry_score, distance_to_resistance, entry_reasons, entry_warnings = (
        score_fast_entry(price, support, resistance, ind_1h["ema20"])
    )
    reasons.extend(entry_reasons)
    warnings.extend(entry_warnings)
    rsi_score, macd_score, momentum_reasons, momentum_warnings = (
        score_fast_momentum(ind_1h)
    )
    indicators_score = rsi_score + macd_score
    reasons.extend(momentum_reasons)
    warnings.extend(momentum_warnings)
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

    grade, decision = grade_fast(total_score, market_state["key"])

    trade_levels = calculate_trade_levels(
        price,
        support,
        resistance,
        atr=ind_1h["atr"],
        profile="fast",
    )
    available_profit_pct = trade_levels["available_profit_pct"]

    grade, decision, safety_warning = apply_fast_safety_filters(
        grade,
        decision,
        available_profit_pct=available_profit_pct,
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
        "strategy_key": "fast",
        "strategy_name": "Fast",
        "strategy_description": "Частые небольшие сделки · 4H + 1H",
        "market_mode": market_state["key"],
        "market_mode_label": market_state["label"],
        "market_mode_description": market_state["description"],
        "price": round(price, 2),
        "support": round(support, 2),
        "support_zone": trade_levels["support_zone"],
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
        "rsi_4h": round(ind_1h["rsi"], 2),
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
