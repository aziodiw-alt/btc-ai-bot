"""Read-only cross-asset recovery calculations for Alpha Rescue."""


SUPPORTED_RESCUE_ASSETS = frozenset({"BTC", "ETH"})


def calculate_rescue_plan(
    base_asset,
    base_quantity,
    cross_entry_price,
    *,
    cross_exit_price=None,
    fee_rate=0.001,
    minimum_net_gain_pct=1.0,
    base_usd_price=None,
    average_cost_usd=None,
):
    base_asset = str(base_asset or "").strip().upper()
    if base_asset not in SUPPORTED_RESCUE_ASSETS:
        raise ValueError("Alpha Rescue supports only BTC or ETH")

    quantity = float(base_quantity)
    entry = float(cross_entry_price)
    fee_rate = float(fee_rate)
    minimum_gain = float(minimum_net_gain_pct) / 100
    if quantity <= 0:
        raise ValueError("Base quantity must be greater than zero")
    if entry <= 0:
        raise ValueError("ETH/BTC entry price must be greater than zero")
    if not 0 <= fee_rate < 1:
        raise ValueError("Fee rate must be between zero and one")
    if minimum_gain < 0:
        raise ValueError("Minimum net gain cannot be negative")

    fee_multiplier = (1 - fee_rate) ** 2
    if cross_exit_price is None:
        if base_asset == "BTC":
            exit_price = entry * (1 + minimum_gain) / fee_multiplier
        else:
            exit_price = entry * fee_multiplier / (1 + minimum_gain)
    else:
        exit_price = float(cross_exit_price)
        if exit_price <= 0:
            raise ValueError("ETH/BTC exit price must be greater than zero")

    if base_asset == "BTC":
        hedge_quantity = quantity / entry * (1 - fee_rate)
        returned_quantity = hedge_quantity * exit_price * (1 - fee_rate)
        required_direction = "UP"
        action = "BTC → ETH → BTC"
    else:
        hedge_quantity = quantity * entry * (1 - fee_rate)
        returned_quantity = hedge_quantity / exit_price * (1 - fee_rate)
        required_direction = "DOWN"
        action = "ETH → BTC → ETH"

    quantity_gain = returned_quantity - quantity
    net_gain_pct = quantity_gain / quantity * 100
    target_met = net_gain_pct + 1e-12 >= minimum_net_gain_pct
    usd_price = (
        float(base_usd_price) if base_usd_price is not None else None
    )
    current_value = quantity * usd_price if usd_price is not None else None
    projected_value = (
        returned_quantity * usd_price if usd_price is not None else None
    )
    average_cost = (
        float(average_cost_usd) if average_cost_usd is not None else None
    )
    original_cost = quantity * average_cost if average_cost is not None else None
    recovery_gap = (
        projected_value - original_cost
        if projected_value is not None and original_cost is not None
        else None
    )

    return {
        "mode": "READ_ONLY",
        "pair": "ETH/BTC",
        "base_asset": base_asset,
        "hedge_asset": "ETH" if base_asset == "BTC" else "BTC",
        "action": action,
        "required_cross_direction": required_direction,
        "base_quantity_before": quantity,
        "hedge_quantity_after_first_trade": hedge_quantity,
        "base_quantity_after": returned_quantity,
        "base_quantity_gain": quantity_gain,
        "net_gain_pct": net_gain_pct,
        "minimum_net_gain_pct": float(minimum_net_gain_pct),
        "target_met": target_met,
        "cross_entry_price": entry,
        "cross_exit_price": exit_price,
        "cross_move_pct": (exit_price / entry - 1) * 100,
        "fee_rate_per_trade": fee_rate,
        "fees_included": 2,
        "base_usd_price": usd_price,
        "current_value_usd": current_value,
        "projected_value_usd_at_same_price": projected_value,
        "average_cost_usd": average_cost,
        "original_cost_usd": original_cost,
        "projected_recovery_gap_usd": recovery_gap,
        "usd_risk_remains": True,
        "warning": (
            "Рост количества монет не гарантирует восстановление USD-стоимости. "
            "План не размещает ордера."
        ),
    }


__all__ = ["SUPPORTED_RESCUE_ASSETS", "calculate_rescue_plan"]
