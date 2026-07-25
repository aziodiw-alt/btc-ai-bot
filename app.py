import os
import sys

import pandas as pd
from flask import Flask, jsonify, render_template, request


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from market import get_klines
from strategy import analyze_strategy


app = Flask(__name__)


def _unix_seconds(value):
    if isinstance(value, pd.Timestamp):
        return int(value.timestamp())

    numeric_value = int(value)

    if numeric_value > 10_000_000_000:
        return numeric_value // 1000

    return numeric_value


@app.route("/")
def home():
    try:
        result = analyze_strategy()
        error = None
    except Exception as exc:
        result = None
        error = str(exc)

    return render_template(
        "index.html",
        result=result,
        error=error,
    )


@app.route("/api/chart-data")
def chart_data():
    try:
        requested_timeframe = request.args.get("timeframe", "240")
        allowed_timeframes = {
            "60": "1H",
            "240": "4H",
            "D": "1D",
        }

        if requested_timeframe not in allowed_timeframes:
            return jsonify({"error": "Неподдерживаемый таймфрейм"}), 400

        frame = get_klines(requested_timeframe, 250)
        result = analyze_strategy()

        candles = [
            {
                "time": _unix_seconds(row.time),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
            }
            for row in frame.itertuples(index=False)
        ]

        return jsonify(
            {
                "candles": candles,
                "timeframe": requested_timeframe,
                "timeframe_label": allowed_timeframes[requested_timeframe],
                "levels": {
                    "current_price": result["price"],
                    "support": result["support"],
                    "resistance": result["resistance"],
                    "buy_zone_1": result["buy_zone_1"],
                    "buy_zone_2": result["buy_zone_2"],
                    "stop_loss": result["stop_loss"],
                    "take_profit_1": result["take_profit_1"],
                    "take_profit_2": result["take_profit_2"],
                },
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True)
