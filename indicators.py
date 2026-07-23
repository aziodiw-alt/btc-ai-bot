from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange


def analyze(df):
    """
    Возвращает основные индикаторы
    """

    close = df["close"]
    high = df["high"]
    low = df["low"]

    rsi = RSIIndicator(close).rsi().iloc[-1]

    ema20 = EMAIndicator(close, window=20).ema_indicator().iloc[-1]
    ema50 = EMAIndicator(close, window=50).ema_indicator().iloc[-1]
    ema200 = EMAIndicator(close, window=200).ema_indicator().iloc[-1]

    macd = MACD(close)

    atr = AverageTrueRange(
        high,
        low,
        close
    ).average_true_range().iloc[-1]

    return {
    "rsi": float(round(rsi, 2)),
    "ema20": float(round(ema20, 2)),
    "ema50": float(round(ema50, 2)),
    "ema200": float(round(ema200, 2)),
    "macd": float(round(macd.macd().iloc[-1], 2)),
    "macd_signal": float(round(macd.macd_signal().iloc[-1], 2)),
    "atr": float(round(atr, 2))
    }