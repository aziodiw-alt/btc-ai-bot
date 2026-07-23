from config import *

print("Telegram:", TELEGRAM_TOKEN is not None)
print("OpenAI:", OPENAI_API_KEY is not None)
print("CoinGlass:", COINGLASS_API_KEY is not None)
print("Bybit:", BYBIT_BASE_URL)
print("Symbol:", SYMBOL)