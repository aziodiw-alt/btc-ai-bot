"""Price-action support and resistance zone detection."""

from statistics import median


def _local_extrema(values, mode, radius=1):
    extrema = []
    for index in range(radius, len(values) - radius):
        value = values[index]
        left = values[index - radius:index]
        right = values[index + 1:index + radius + 1]
        neighbours = left + right
        if not neighbours:
            continue
        if mode == "low" and value <= min(neighbours):
            extrema.append((index, value))
        elif mode == "high" and value >= max(neighbours):
            extrema.append((index, value))
    return extrema


def _cluster_extrema(extrema, tolerance):
    clusters = []
    for item in sorted(extrema, key=lambda candidate: candidate[1]):
        index, price = item[:2]
        volume = item[2] if len(item) > 2 else 0.0
        best = None
        best_distance = None
        for cluster in clusters:
            distance = abs(price - cluster["center"])
            if distance <= tolerance and (
                best_distance is None or distance < best_distance
            ):
                best = cluster
                best_distance = distance
        if best is None:
            clusters.append(
                {
                    "center": price,
                    "prices": [price],
                    "indices": [index],
                    "volumes": [volume],
                }
            )
        else:
            best["prices"].append(price)
            best["indices"].append(index)
            best["volumes"].append(volume)
            best["center"] = median(best["prices"])
    return clusters


def _strongest_zone(
    clusters, current_price, side, sample_size, typical_volume=0.0
):
    eligible = [
        cluster
        for cluster in clusters
        if len(cluster["prices"]) >= 2
        and (
            cluster["center"] < current_price
            if side == "support"
            else cluster["center"] > current_price
        )
    ]
    if not eligible:
        return None

    def score(cluster):
        touches = len(cluster["prices"])
        freshness = max(cluster["indices"]) / max(sample_size - 1, 1)
        distance = abs(current_price - cluster["center"]) / current_price
        volume_score = 0.0
        if typical_volume > 0:
            average_volume = sum(cluster["volumes"]) / touches
            volume_score = min(average_volume / typical_volume, 2.0) * 2
        return touches * 10 + freshness * 3 + volume_score - distance

    return max(eligible, key=score)["center"]


def detect_strong_levels(frame, lookback=50):
    """Return repeatedly tested levels, or extremes when history is sparse."""
    recent = frame.tail(lookback)
    if recent.empty:
        raise ValueError("Cannot calculate levels from an empty candle set")

    lows = [float(value) for value in recent["low"]]
    highs = [float(value) for value in recent["high"]]
    fallback = (min(lows), max(highs))
    if len(recent) < 5:
        return fallback

    if "close" in recent:
        current_price = float(recent["close"].iloc[-1])
    else:
        current_price = (lows[-1] + highs[-1]) / 2

    candle_ranges = [high - low for high, low in zip(highs, lows)]
    positive_ranges = [value for value in candle_ranges if value > 0]
    typical_range = (
        median(positive_ranges) if positive_ranges else current_price * 0.001
    )
    tolerance = max(typical_range * 0.20, current_price * 0.0015)
    volumes = (
        [float(value) for value in recent["volume"]]
        if "volume" in recent
        else [0.0] * len(recent)
    )
    positive_volumes = [value for value in volumes if value > 0]
    typical_volume = median(positive_volumes) if positive_volumes else 0.0

    reactions = _local_extrema(lows, "low") + _local_extrema(highs, "high")
    reactions_with_volume = [
        (index, price, volumes[index]) for index, price in reactions
    ]

    # Cluster highs and lows together so a broken resistance can become
    # support (and a broken support can become resistance).
    reaction_clusters = _cluster_extrema(
        reactions_with_volume,
        tolerance,
    )
    support = _strongest_zone(
        reaction_clusters,
        current_price,
        "support",
        len(recent),
        typical_volume,
    )
    resistance = _strongest_zone(
        reaction_clusters,
        current_price,
        "resistance",
        len(recent),
        typical_volume,
    )
    return (
        float(support if support is not None else fallback[0]),
        float(resistance if resistance is not None else fallback[1]),
    )


__all__ = ["detect_strong_levels"]
