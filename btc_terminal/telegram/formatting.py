"""Telegram-specific presentation of strategy analysis results."""


def format_number(value, decimals=0):
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", " ")


def format_zone(zone):
    if isinstance(zone, (list, tuple)) and len(zone) == 2:
        low, high = sorted(zone)
        return f"{format_number(low)} – {format_number(high)}"
    return str(zone)


def format_analysis(result):
    display_symbol = result.get("display_symbol", "BTC/USDT")
    exchange_name = (
        "OKX"
        if str(result.get("exchange", "bybit")).lower() == "okx"
        else "Bybit"
    )
    price_decimals = 2 if display_symbol.startswith("ETH") else 0
    reasons = "\n".join(
        f"• {item}" for item in result.get("reasons", [])
    )
    warnings = "\n".join(
        f"• {item}" for item in result.get("warnings", [])
    )

    return f"""📊 {display_symbol}
🏦 Биржа: {exchange_name}

💰 Цена: {format_number(result["price"], price_decimals)}

🧭 Режим: {result.get("market_mode_label", result.get("market_mode", "—"))}
📈 Trend: {result["trend_score"]}/40
🎯 Entry: {result["entry_score"]}/20
📊 Indicators: {result["indicators_score"]}/10
🌍 Sentiment: {result["sentiment_score"]}/30

🏆 Итог: {result["total_score"]}/100
⭐ Grade: {result["grade"]}

📌 Решение стратегии:
{result["decision"]}

🎯 Buy Zone 1: {format_zone(result["buy_zone_1"])}
🎯 Buy Zone 2: {format_zone(result["buy_zone_2"])}
🛑 Stop Loss: {format_number(result["stop_loss"])}
💰 Take Profit 1: {format_number(result["take_profit_1"])}
🚀 Take Profit 2: {format_number(result["take_profit_2"])}

✅ Причины:
{reasons or "• Нет"}

⚠️ Предупреждения:
{warnings or "• Нет"}"""


__all__ = ["format_number", "format_zone", "format_analysis"]
