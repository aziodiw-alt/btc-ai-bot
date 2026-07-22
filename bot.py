import os
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

keyboard = ReplyKeyboardMarkup([["📊 Анализ BTC"]], resize_keyboard=True)


def get_bybit_klines(symbol="BTCUSDT", interval="240", limit=250):
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "spot",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    r = requests.get(url, params=params, timeout=15)
    data = r.json()

    if data.get("retCode") != 0:
        raise Exception(data.get("retMsg", "Ошибка Bybit API"))

    rows = data["result"]["list"]
    df = pd.DataFrame(rows, columns=[
        "time", "open", "high", "low", "close", "volume", "turnover"
    ])

    df = df.astype({
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "volume": float,
    })

    df["time"] = pd.to_datetime(df["time"].astype(int), unit="ms")
    df = df.sort_values("time").reset_index(drop=True)

    return df


def add_indicators(df):
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma30"] = df["close"].rolling(30).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


def support_resistance(df, lookback=50):
    recent = df.tail(lookback)
    support = recent["low"].min()
    resistance = recent["high"].max()
    return support, resistance


def analyze_market():
    d1 = add_indicators(get_bybit_klines(interval="D", limit=250))
    h4 = add_indicators(get_bybit_klines(interval="240", limit=250))

    last_d = d1.iloc[-1]
    last_h = h4.iloc[-1]

    price = float(last_h["close"])
    support, resistance = support_resistance(h4, 50)

    score = 0
    reasons_good = []
    reasons_bad = []

    # 1D trend
    if last_d["close"] > last_d["ma20"] and last_d["ma5"] > last_d["ma10"]:
        score += 15
        reasons_good.append("1D тренд бычий")
        d1_status = "🟢 Бычий"
    else:
        score += 5
        reasons_bad.append("1D тренд не идеальный")
        d1_status = "🟡 Неуверенный"

    # 4H trend
    if last_h["close"] > last_h["ma20"] and last_h["ma5"] > last_h["ma10"]:
        score += 15
        reasons_good.append("4H тренд бычий")
        h4_status = "🟢 Бычий"
    else:
        score += 5
        reasons_bad.append("4H тренд слабый")
        h4_status = "🟡 Неуверенный"

    # EMA200
    if last_h["close"] > last_h["ema200"]:
        score += 10
        ema_status = "🟢 Выше EMA200"
    else:
        score += 3
        ema_status = "🔴 Ниже EMA200"

    # RSI
    rsi = float(last_h["rsi"])
    if 45 <= rsi <= 62:
        score += 12
        rsi_status = "🟢 Нормальный"
    elif 62 < rsi <= 70:
        score += 6
        rsi_status = "🟡 Высокий"
    elif rsi < 45:
        score += 6
        rsi_status = "🟡 Слабый"
    else:
        score += 2
        rsi_status = "🔴 Перегрет"

    # MACD
    if last_h["macd"] > last_h["macd_signal"]:
        score += 10
        macd_status = "🟢 Бычий"
    else:
        score += 3
        macd_status = "🟡 Слабый"

    # Volume
    if last_h["volume"] > last_h["vol_ma20"]:
        score += 8
        volume_status = "🟢 Выше среднего"
    else:
        score += 4
        volume_status = "🟡 Ниже среднего"

    # Position vs resistance
    distance_to_resistance = (resistance - price) / price * 100
    if distance_to_resistance >= 1.8:
        score += 10
        rr_status = "🟢 Хороший запас до сопротивления"
    elif distance_to_resistance >= 1.0:
        score += 5
        rr_status = "🟡 Средний запас"
    else:
        score += 1
        rr_status = "🔴 Цена близко к сопротивлению"

    # Pullback quality
    distance_to_ma20 = abs(price - last_h["ma20"]) / price * 100
    if distance_to_ma20 <= 0.8:
        score += 10
        pullback_status = "🟢 Хорошо близко к MA20"
    elif distance_to_ma20 <= 1.6:
        score += 6
        pullback_status = "🟡 Нормально"
    else:
        score += 2
        pullback_status = "🔴 Далеко от MA20"

    score = min(score, 95)

    buy1_high = price * 0.995
    buy1_low = price * 0.991
    sell1 = buy1_high * 1.018

    buy2_high = price * 0.987
    buy2_low = price * 0.982
    sell2 = buy2_high * 1.018

    if score >= 88:
        signal = "A+"
        decision = "✅ Можно ставить лимитку, но не покупать по рынку"
    elif score >= 78:
        signal = "A"
        decision = "⏳ Ждать отката в зону покупки"
    elif score >= 65:
        signal = "B"
        decision = "🟡 Только маленький объем или пропуск"
    else:
        signal = "C"
        decision = "❌ Не покупать"

    return f"""
BTC/USDT

Цена: {price:,.0f}

📈 1D:
{d1_status}

📊 4H:
{h4_status}

EMA200:
{ema_status}

RSI 4H:
{rsi:.1f} — {rsi_status}

MACD:
{macd_status}

Объем:
{volume_status}

Reward/Risk:
{rr_status}

Откат:
{pullback_status}

Поддержка 4H:
{support:,.0f}

Сопротивление 4H:
{resistance:,.0f}

🎯 Покупка 1:
{buy1_low:,.0f} – {buy1_high:,.0f}

💰 Продажа 1:
{sell1:,.0f}

🎯 Покупка 2:
{buy2_low:,.0f} – {buy2_high:,.0f}

💰 Продажа 2:
{sell2:,.0f}

⭐ Сигнал:
{signal}

Entry Score:
{score}/100

✅ Решение:
{decision}

⚠️ Правило:
По рынку не входить, только лимиткой на откате.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Нажми кнопку ниже:", reply_markup=keyboard)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if "анализ btc" in text:
        await update.message.reply_text("Получаю данные Bybit и считаю индикаторы... ⏳")
        try:
            result = analyze_market()
            await update.message.reply_text(result, reply_markup=keyboard)
        except Exception as e:
            await update.message.reply_text(f"Ошибка анализа: {e}", reply_markup=keyboard)
    else:
        await update.message.reply_text("Нажми кнопку: 📊 Анализ BTC", reply_markup=keyboard)


def main():
    if not TELEGRAM_TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не найден в .env")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()