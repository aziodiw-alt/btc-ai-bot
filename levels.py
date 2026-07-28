"""Shared support, resistance, entry-zone, stop, and target calculations."""


def calculate_support_resistance(frame, lookback=50):
    """Return the lowest low and highest high in the selected window."""
    recent = frame.tail(lookback)

    if recent.empty:
        raise ValueError("Cannot calculate levels from an empty candle set")

    return float(recent["low"].min()), float(recent["high"].max())


def calculate_trade_levels(
    price,
    support,
    resistance,
    *,
    profile="swing",
):
    """Calculate all displayed trade levels from one price snapshot."""
    price = float(price)
    support = float(support)
    resistance = float(resistance)

    if price <= 0 or support <= 0 or resistance <= 0:
        raise ValueError("Price, support, and resistance must be positive")

    if profile == "fast":
        buy_zone_1 = [round(price * 0.994, 2), round(price * 0.997, 2)]
        buy_zone_2 = [round(price * 0.988, 2), round(price * 0.992, 2)]
        planned_entry = buy_zone_1[1]
        stop_loss = round(max(support * 0.998, planned_entry * 0.993), 2)
        safe_resistance = round(resistance * 0.998, 2)
        target_multipliers = (1.008, 1.011)
        minimum_profit_pct = 0.8
    elif profile == "swing":
        buy_zone_1 = [round(price * 0.991, 2), round(price * 0.995, 2)]
        buy_zone_2 = [round(price * 0.982, 2), round(price * 0.987, 2)]
        planned_entry = buy_zone_1[1]
        stop_loss = round(support * 0.995, 2)
        safe_resistance = round(resistance * 0.995, 2)
        target_multipliers = (1.015, 1.020)
        minimum_profit_pct = 1.5
    else:
        raise ValueError(f"Unknown trade-level profile: {profile}")

    available_profit_pct = (
        (safe_resistance - planned_entry) / planned_entry * 100
        if safe_resistance > planned_entry
        else 0.0
    )

    return {
        "buy_zone_1": buy_zone_1,
        "buy_zone_2": buy_zone_2,
        "stop_loss": stop_loss,
        "take_profit_1": round(
            min(planned_entry * target_multipliers[0], safe_resistance),
            2,
        ),
        "take_profit_2": round(
            min(planned_entry * target_multipliers[1], safe_resistance),
            2,
        ),
        "planned_entry": planned_entry,
        "safe_resistance": safe_resistance,
        "available_profit_pct": round(available_profit_pct, 2),
        "target_available": available_profit_pct >= minimum_profit_pct,
    }
