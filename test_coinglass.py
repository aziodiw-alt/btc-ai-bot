import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("COINGLASS_API_KEY")

if not API_KEY:
    raise RuntimeError("COINGLASS_API_KEY is not configured")

url = "https://open-api-v4.coinglass.com/api/futures/global-long-short-account-ratio/history"

headers = {
    "CG-API-KEY": API_KEY,
}

params = {
    "exchange": "Binance",
    "symbol": "BTCUSDT",
    "interval": "h4",
    "limit": 5
}

response = requests.get(url, headers=headers, params=params, timeout=20)

print("STATUS:", response.status_code)
print(response.text[:1000])
