import asyncio
import os

from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_report import generate_report
from strategy import analyze_strategy


load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

keyboard = ReplyKeyboardMarkup(
    [["📊 Анализ BTC"]],
    resize_keyboard=True,
)


def format_number(value):
    """Красивое отображение цены без лишних десятичных знаков."""
    return f"{float(value):,.0f}".replace(",", " ")


def format_zone(zone):
    """Преобразует список или кортеж из двух цен в понятный диапазон."""
    if isinstance(zone, (list, tuple)) and len(zone) == 2:
        low, high = sorted(zone)
        return f"{format_number(low)} – {format_number(high)}"

    return str(zone)


def format_analysis(result):
    reasons = "\n".join(f"• {item}" for item in result.get("reasons", []))
    warnings = "\n".join(f"• {item}" for item in result.get("warnings", []))

    if not reasons:
        reasons = "• Нет дополнительных положительных факторов"

    if not warnings:
        warnings = "• Существенных предупреждений нет"

    return f"""📊 BTC/USDT

💰 Цена: {format_number(result["price"])}

📈 Trend: {result["trend_score"]}/40
🎯 Entry: {result["entry_score"]}/20
📊 Indicators: {result["indicators_score"]}/10
🌍 Sentiment: {result["sentiment_score"]}/30

🏆 Итог: {result["total_score"]}/100
⭐ Grade: {result["grade"]}

🤖 Решение:
{result["decision"]}

🎯 Buy Zone 1:
{format_zone(result["buy_zone_1"])}

🎯 Buy Zone 2:
{format_zone(result["buy_zone_2"])}

🛑 Stop Loss:
{format_number(result["stop_loss"])}

💰 Take Profit 1:
{format_number(result["take_profit_1"])}

🚀 Take Profit 2:
{format_number(result["take_profit_2"])}

✅ Причины:
{reasons}

⚠️ Предупреждения:
{warnings}"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Нажми кнопку ниже:",
        reply_markup=keyboard,
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").lower()

    if "анализ btc" not in text:
        await update.message.reply_text(
            "Нажми кнопку: 📊 Анализ BTC",
            reply_markup=keyboard,
        )
        return

    await update.message.reply_text(
        "Получаю данные Bybit и считаю индикаторы... ⏳"
    )

    try:
        # Синхронные сетевые запросы запускаются отдельно, чтобы бот не зависал.
        result = await asyncio.to_thread(analyze_strategy)

        await update.message.reply_text(
            format_analysis(result),
            reply_markup=keyboard,
        )

        await update.message.reply_text("Готовлю AI-комментарий... 🤖")

        ai_text = await asyncio.to_thread(generate_report, result)

        await update.message.reply_text(
            f"🤖 AI-комментарий:\n\n{ai_text}",
            reply_markup=keyboard,
        )

    except Exception as error:
        await update.message.reply_text(
            f"Ошибка анализа: {error}",
            reply_markup=keyboard,
        )


def main():
    if not TELEGRAM_TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не найден в .env")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
