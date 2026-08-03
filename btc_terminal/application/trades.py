"""Pure trade calculations, independent from HTTP and persistence."""

DEFAULT_FEE_RATE = 0.001


def calculate_sell_advice(
    fifo_stats,
    current_price=None,
    pending_sell_quantity=0,
    fee_rate=DEFAULT_FEE_RATE,
    quote_currency="USDT",
):
    quantity = float(fifo_stats.get("open_quantity") or 0)
    open_cost = float(fifo_stats.get("open_cost") or 0)
    if quantity <= 1e-12 or open_cost <= 0:
        return {
            "available": False,
            "reason": "Нет остатка исполненных покупок для расчёта.",
        }

    average_buy_price = open_cost / quantity
    target_price_15 = average_buy_price * 1.015 / (1 - fee_rate)
    target_price_20 = average_buy_price * 1.020 / (1 - fee_rate)
    reserved_quantity = min(
        max(float(pending_sell_quantity or 0), 0), quantity
    )
    free_quantity = max(quantity - reserved_quantity, 0)
    market_price = float(current_price) if current_price is not None else None
    free_value = (
        free_quantity * market_price
        if market_price and market_price > 0
        else None
    )
    return {
        "available": True,
        "quantity": quantity,
        "open_cost": open_cost,
        "average_buy_price": average_buy_price,
        "target_price_15": target_price_15,
        "target_price_20": target_price_20,
        "profit_15": open_cost * 0.015,
        "profit_20": open_cost * 0.020,
        "reserved_quantity": reserved_quantity,
        "free_quantity": free_quantity,
        "free_value_usdt": free_value,
        "free_value_quote": free_value,
        "quote_currency": str(quote_currency or "USDT").upper(),
        "current_price": market_price,
        "distance_15_pct": (
            (target_price_15 / market_price - 1) * 100
            if market_price and market_price > 0 else None
        ),
        "distance_20_pct": (
            (target_price_20 / market_price - 1) * 100
            if market_price and market_price > 0 else None
        ),
        "fee_rate": fee_rate,
    }


def calculate_okx_fifo_statistics(trades, instrument):
    instrument = str(instrument or "").upper()
    base_currency, _, quote_currency = instrument.partition("-")
    lots = []
    unmatched_sell_quantity = 0.0
    matching_trades = sorted(
        (
            trade for trade in (trades or [])
            if str(trade.get("instrument") or "").upper() == instrument
        ),
        key=lambda trade: str(trade.get("created_at") or ""),
    )
    for trade in matching_trades:
        side = str(trade.get("side") or "").upper()
        size = max(float(trade.get("size") or 0), 0)
        value = max(float(trade.get("value") or 0), 0)
        fee = float(trade.get("fee") or 0)
        fee_currency = str(trade.get("fee_currency") or "").upper()
        if side == "BUY":
            acquired_quantity = size
            cost = value
            if fee_currency == base_currency:
                acquired_quantity = max(size + fee, 0)
            elif fee_currency == quote_currency:
                cost += abs(fee)
            if acquired_quantity > 1e-12 and cost > 0:
                lots.append({
                    "quantity": acquired_quantity,
                    "unit_cost": cost / acquired_quantity,
                })
            continue
        if side != "SELL":
            continue
        quantity_to_remove = size
        if fee_currency == base_currency:
            quantity_to_remove += abs(fee)
        while quantity_to_remove > 1e-12 and lots:
            lot = lots[0]
            matched = min(quantity_to_remove, lot["quantity"])
            lot["quantity"] -= matched
            quantity_to_remove -= matched
            if lot["quantity"] <= 1e-12:
                lots.pop(0)
        unmatched_sell_quantity += max(quantity_to_remove, 0)
    return {
        "instrument": instrument,
        "execution_count": len(matching_trades),
        "open_quantity": sum(lot["quantity"] for lot in lots),
        "open_cost": sum(
            lot["quantity"] * lot["unit_cost"] for lot in lots
        ),
        "unmatched_sell_quantity": unmatched_sell_quantity,
    }


def add_okx_order_profit_estimates(
    orders, fifo_stats, fee_rate=DEFAULT_FEE_RATE
):
    enriched_orders = [dict(order) for order in (orders or [])]
    open_quantity = max(float(fifo_stats.get("open_quantity") or 0), 0)
    open_cost = max(float(fifo_stats.get("open_cost") or 0), 0)
    average_buy_price = (
        open_cost / open_quantity if open_quantity > 1e-12 else None
    )
    instrument = str(fifo_stats.get("instrument") or "").upper()
    remaining_position = open_quantity
    for order in enriched_orders:
        order.update({
            "estimated_profit_quote": None,
            "estimated_profit_pct": None,
            "average_buy_price": average_buy_price,
            "matched_quantity": 0.0,
            "profit_coverage_pct": 0.0,
            "profit_is_complete": False,
        })
    sell_indices = sorted(
        (
            index for index, order in enumerate(enriched_orders)
            if str(order.get("side") or "").upper() == "SELL"
            and (
                not instrument
                or str(order.get("instrument") or "").upper() == instrument
            )
        ),
        key=lambda index: str(enriched_orders[index].get("created_at") or ""),
    )
    for index in sell_indices:
        order = enriched_orders[index]
        order_quantity = max(float(order.get("remaining_size") or 0), 0)
        order_price = max(float(order.get("price") or 0), 0)
        if (
            average_buy_price is None
            or order_quantity <= 1e-12
            or order_price <= 0
        ):
            continue
        matched_quantity = min(order_quantity, remaining_position)
        remaining_position = max(remaining_position - matched_quantity, 0)
        order["matched_quantity"] = matched_quantity
        order["profit_coverage_pct"] = matched_quantity / order_quantity * 100
        order["profit_is_complete"] = (
            order_quantity - matched_quantity <= 1e-12
        )
        if matched_quantity <= 1e-12:
            continue
        matched_cost = matched_quantity * average_buy_price
        estimated_profit = (
            matched_quantity * order_price * (1 - fee_rate) - matched_cost
        )
        order["estimated_profit_quote"] = estimated_profit
        order["estimated_profit_pct"] = (
            estimated_profit / matched_cost * 100
            if matched_cost > 0 else None
        )
    return enriched_orders


def normalize_zone(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        first = float(value[0])
        second = float(value[1])
        return min(first, second), max(first, second)
    center = float(value)
    return center, center


def distance_to_zone_pct(price, zone):
    low, high = zone
    if low <= price <= high:
        return 0.0
    nearest = low if price < low else high
    return abs(price - nearest) / max(price, 1e-12) * 100


def classify_order_strategy(order_price, side, strategy_levels):
    price = float(order_price)
    side = str(side).upper()
    candidates = []
    for strategy_key, result in (strategy_levels or {}).items():
        strategy_name = {
            "fast": "Fast",
            "alpha": "Alpha",
        }.get(strategy_key, "Swing")
        if side == "BUY":
            for zone_key, zone_label in (
                ("buy_zone_1", "Buy Zone 1"),
                ("buy_zone_2", "Buy Zone 2"),
            ):
                if result.get(zone_key) is None:
                    continue
                zone = normalize_zone(result[zone_key])
                distance = distance_to_zone_pct(price, zone)
                center_distance = abs(price - sum(zone) / 2) / price * 100
                candidates.append({
                    "strategy_key": strategy_key,
                    "strategy_name": strategy_name,
                    "distance": distance,
                    "tie_distance": center_distance,
                    "level": zone_label,
                })
        elif side == "SELL":
            for target_key, target_label in (
                ("take_profit_1", "TP1"),
                ("take_profit_2", "TP2"),
            ):
                if result.get(target_key) is None:
                    continue
                target = float(result[target_key])
                distance = abs(price - target) / price * 100
                candidates.append({
                    "strategy_key": strategy_key,
                    "strategy_name": strategy_name,
                    "distance": distance,
                    "tie_distance": distance,
                    "level": target_label,
                })
    if not candidates:
        return {
            "strategy_key": None,
            "strategy_confidence": 0,
            "strategy_reason": "Недостаточно данных для определения",
        }
    candidates.sort(key=lambda item: (item["distance"], item["tie_distance"]))
    best = candidates[0]
    distance = best["distance"]
    if distance == 0:
        confidence = 95
        reason = f"Цена внутри {best['strategy_name']} {best['level']}"
    elif distance <= 0.35:
        confidence = 88
        reason = (
            f"Цена на {distance:.2f}% от "
            f"{best['strategy_name']} {best['level']}"
        )
    elif distance <= 1.0:
        confidence = 70
        reason = (
            f"Цена на {distance:.2f}% от "
            f"{best['strategy_name']} {best['level']}"
        )
    else:
        return {
            "strategy_key": None,
            "strategy_confidence": 0,
            "strategy_reason": (
                f"Ближайший уровень дальше чем на {distance:.2f}%"
            ),
        }
    return {
        "strategy_key": best["strategy_key"],
        "strategy_confidence": confidence,
        "strategy_reason": reason,
    }


def summarize_open_orders(orders):
    open_orders = [
        order for order in (orders or []) if order["status"] == "OPEN"
    ]
    expected_profit = sum(
        float(order["estimated_profit_usdt"])
        for order in open_orders
        if order["estimated_profit_usdt"] is not None
    )
    expected_cost = sum(
        float(order["estimated_cost_usdt"])
        for order in open_orders
        if order["estimated_cost_usdt"] is not None
    )
    sell_quantity = sum(
        float(order["order_quantity"])
        for order in open_orders
        if order["side"] == "SELL"
    )
    matched_sell_quantity = sum(
        float(order["matched_quantity"])
        for order in open_orders
        if order["side"] == "SELL"
    )
    unmatched_sell_quantity = max(
        sell_quantity - matched_sell_quantity, 0
    )
    summary = {
        "count": len(open_orders),
        "buy_count": sum(
            order["side"] == "BUY" for order in open_orders
        ),
        "sell_count": sum(
            order["side"] == "SELL" for order in open_orders
        ),
        "buy_value": sum(
            float(order["order_value"])
            for order in open_orders if order["side"] == "BUY"
        ),
        "sell_value": sum(
            float(order["order_value"])
            for order in open_orders if order["side"] == "SELL"
        ),
        "expected_profit": expected_profit,
        "expected_profit_pct": (
            expected_profit / expected_cost * 100
            if expected_cost > 0 else None
        ),
        "profit_coverage_pct": (
            matched_sell_quantity / sell_quantity * 100
            if sell_quantity > 0 else None
        ),
        "profit_is_complete": (
            sell_quantity > 0 and unmatched_sell_quantity <= 1e-12
        ),
        "matched_sell_quantity": matched_sell_quantity,
        "unmatched_sell_quantity": unmatched_sell_quantity,
        "calculated_sell_count": sum(
            order["estimated_profit_usdt"] is not None
            for order in open_orders if order["side"] == "SELL"
        ),
    }
    return open_orders, summary


__all__ = [
    "DEFAULT_FEE_RATE",
    "calculate_sell_advice",
    "calculate_okx_fifo_statistics",
    "add_okx_order_profit_estimates",
    "normalize_zone",
    "distance_to_zone_pct",
    "classify_order_strategy",
    "summarize_open_orders",
]
