import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# CoinGlass
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY")

# Bybit
BYBIT_BASE_URL = "https://api.bybit.com"

# Основная торговая пара
SYMBOL = "BTCUSDT"

# Таймфреймы
TIMEFRAME_1D = "D"
TIMEFRAME_4H = "240"
# ==========================
# Strategy Settings
# ==========================

# RSI
RSI_MIN = 45
RSI_MAX = 60

# Entry Score
GRADE_A_PLUS = 90
GRADE_A = 80
GRADE_B = 70
GRADE_C = 60

# Баллы

SCORE_EMA200 = 20
SCORE_EMA20 = 15
SCORE_RSI = 15
SCORE_MACD = 15
SCORE_VOLUME = 10
SCORE_SUPPORT = 10
SCORE_RESISTANCE = 15

# Цель прибыли

TARGET_PROFIT_MIN = 1.5
TARGET_PROFIT_MAX = 2.0