from market import get_klines
from indicators import analyze

df = get_klines("240", 250)

result = analyze(df)

print(result)