"""Support, resistance, entry-zone, stop, and target calculations."""

from btc_terminal.strategy.level_zones import detect_strong_levels


def calculate_support_resistance(frame, lookback=50):
    """Return strong repeatedly tested levels from the selected window."""
    return detect_strong_levels(frame, lookback=lookback)


def calculate_trade_levels(
    price,
    support,
    resistance,
    *,
    atr=None,
    profile="swing",
):
    """Calculate support-aware entry zones, stop, and profit targets."""
    price = float(price)
    support = float(support)
    resistance = float(resistance)
    atr = float(atr or 0)

    if price <= 0 or support <= 0 or resistance <= 0:
        raise ValueError("Price, support, and resistance must be positive")

    if profile == "fast":
        safe_resistance = round(resistance * 0.998, 2)
        target_multipliers = (1.008, 1.011)
        minimum_profit_pct = 0.8
        zone_width = max(atr * 0.12, price * 0.0012)
        second_zone_gap = max(atr * 0.45, price * 0.003)
        stop_gap = max(atr * 0.35, price * 0.0025)
    elif profile == "swing":
        safe_resistance = round(resistance * 0.995, 2)
        target_multipliers = (1.015, 1.020)
        minimum_profit_pct = 1.5
        zone_width = max(atr * 0.18, price * 0.0015)
        second_zone_gap = max(atr * 0.70, price * 0.005)
        stop_gap = max(atr * 0.50, price * 0.004)
    else:
        raise ValueError(f"Unknown trade-level profile: {profile}")

    # A support above the market has already been broken and must not be used
    # as a buy anchor. In that case, use a conservative fallback below price.
    anchor = support if support < price else price - max(atr * 0.5, price * 0.006)
    zone_1_high = min(anchor + zone_width, price * 0.997)
    zone_1_low = anchor - zone_width

    zone_2_high = zone_1_low - second_zone_gap
    zone_2_low = zone_2_high - 2 * zone_width

    buy_zone_1 = [round(zone_1_low, 2), round(zone_1_high, 2)]
    buy_zone_2 = [round(zone_2_low, 2), round(zone_2_high, 2)]
    support_zone = [
        round(anchor - zone_width, 2),
        round(anchor + zone_width, 2),
    ]
    planned_entry = buy_zone_1[1]
    stop_loss = round(buy_zone_2[0] - stop_gap, 2)

    available_profit_pct = (
        (safe_resistance - planned_entry) / planned_entry * 100
        if safe_resistance > planned_entry
        else 0.0
    )

    return {
        "buy_zone_1": buy_zone_1,
        "buy_zone_2": buy_zone_2,
        "support_zone": support_zone,
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


__all__ = ["calculate_support_resistance", "calculate_trade_levels"]
