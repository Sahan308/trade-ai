"""Candle validation: malformed rows, duplicates, ordering and gaps."""
import math
from datetime import datetime, timezone

from ..providers.base import INTERVAL_MS, Candle


def _f(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return math.nan
    return x


def validate_klines(rows: list, interval: str) -> tuple[list[Candle], int, int]:
    """Return (candles sorted by open time, dropped_count, gap_count). Later duplicates win."""
    by_time: dict[int, Candle] = {}
    dropped = 0
    for r in rows or []:
        try:
            t = int(r[0])
            o, h, l, c, v = (_f(x) for x in r[1:6])
        except (TypeError, ValueError, IndexError):
            dropped += 1
            continue
        values = (o, h, l, c, v)
        if t <= 0 or not all(math.isfinite(x) for x in values) or h < max(o, c) or l > min(o, c) or v < 0:
            dropped += 1
            continue
        by_time[t] = Candle(datetime.fromtimestamp(t / 1000, tz=timezone.utc), o, h, l, c, v)
    times = sorted(by_time)
    step = INTERVAL_MS[interval]
    gaps = sum(max(0, round((b - a) / step) - 1) for a, b in zip(times, times[1:]))
    return [by_time[t] for t in times], dropped, gaps
