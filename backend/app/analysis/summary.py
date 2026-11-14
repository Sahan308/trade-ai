"""Run every indicator over a candle series and return the latest readings plus recent patterns."""
from __future__ import annotations

from ..providers.base import INTERVAL_MS
from . import indicators as ind
from .patterns import detect_candlestick_patterns, double_tops_bottoms, swing_points


def _last(x):
    return x[-1] if x else None


def analyze(t, o, h, l, c, v, interval: str, pattern_window: int = 30) -> dict:
    n = len(c)
    m = ind.macd(c)
    st = ind.stochastic(h, l, c)
    bb = ind.bollinger(c)
    kc = ind.keltner(h, l, c)
    dmi = ind.adx(h, l, c)
    sup = ind.supertrend(h, l, c)
    ich = ind.ichimoku(h, l, c)
    latest = {
        "sma_20": _last(ind.sma(c, 20)), "sma_50": _last(ind.sma(c, 50)), "ema_20": _last(ind.ema(c, 20)),
        "ema_50": _last(ind.ema(c, 50)), "wma_20": _last(ind.wma(c, 20)), "vwma_20": _last(ind.vwma(c, v, 20)),
        "rsi_14": _last(ind.rsi(c)), "macd": _last(m["macd"]), "macd_signal": _last(m["signal"]), "macd_histogram": _last(m["histogram"]),
        "stoch_k": _last(st["k"]), "stoch_d": _last(st["d"]), "cci_20": _last(ind.cci(h, l, c)), "mfi_14": _last(ind.mfi(h, l, c, v)),
        "atr_14": _last(ind.atr(h, l, c)), "bb_upper": _last(bb["upper"]), "bb_middle": _last(bb["middle"]), "bb_lower": _last(bb["lower"]),
        "kc_upper": _last(kc["upper"]), "kc_middle": _last(kc["middle"]), "kc_lower": _last(kc["lower"]),
        "adx_14": _last(dmi["adx"]), "plus_di": _last(dmi["plus_di"]), "minus_di": _last(dmi["minus_di"]),
        "supertrend": _last(sup["supertrend"]), "supertrend_direction": _last(sup["direction"]),
        "ichimoku_tenkan": _last(ich["tenkan"]), "ichimoku_kijun": _last(ich["kijun"]),
        "ichimoku_span_a": _last(ich["span_a"]), "ichimoku_span_b": _last(ich["span_b"]),
        "obv": _last(ind.obv(c, v)), "vwap": _last(ind.vwap(t, h, l, c, v)), "psar": _last(ind.parabolic_sar(h, l)),
    }
    pats = [p for p in detect_candlestick_patterns(o, h, l, c) if p["index"] >= n - pattern_window]
    for p in pats:
        p["time"] = t[p["index"]]
    forms = double_tops_bottoms(h, l, c)
    for f in forms:
        f["times"] = [t[i] for i in f["points"]]
    return {
        "bars": n,
        "latest": latest,
        "volume_profile": ind.volume_profile(h, l, c, v),
        "fibonacci": ind.fibonacci(h, l),
        "pivots": ind.pivots(t, h, l, c, INTERVAL_MS[interval]),
        "patterns": pats,
        "formations": forms,
        "swings": swing_points(h, l),
    }
