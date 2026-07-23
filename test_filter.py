from market import get_ticker, get_klines
from indicators import analyze
from trade_filter import evaluate

ticker = get_ticker()

df = get_klines("240", 250)

ind = analyze(df)

result = evaluate(ind, ticker["price"])

print(result)