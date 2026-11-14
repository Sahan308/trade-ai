"""Rule-based candlestick patterns and chart formations.

Patterns are CONTEXT, not predictions. Each hit names the candle indices that triggered it.
Shared definitions (all relative to the candle itself or to recent candles):
  body = |C−O|, range = H−L, upper = H−max(O,C), lower = min(O,C)−L
  avg_body = mean body of the previous 10 candles (needs 10 bars of history)
  downtrend before i: close[i−1] < close[i−6];  uptrend: close[i−1] > close[i−6]
Thresholds are module constants so they are documented and tested.
"""
from __future__ import annotations

from collections.abc import Sequence

DOJI_BODY = 0.1          # body ≤ 10% of range
SMALL_BODY = 0.3         # body ≤ 30% of range
LONG_BODY = 1.3          # body ≥ 1.3 × avg_body
SHADOW_MULT = 2.0        # long shadow ≥ 2 × body
TINY_SHADOW = 0.1        # shadow ≤ 10% of range
MARUBOZU_SHADOW = 0.05   # each shadow ≤ 5% of range
TWEEZER_TOL = 0.001      # highs/lows equal within 0.1%
HISTORY = 10             # bars needed before a pattern can be reported


class C:
    __slots__ = ("o", "h", "l", "c")

    def __init__(self, o, h, l, c):
        self.o, self.h, self.l, self.c = o, h, l, c

    @property
    def body(self): return abs(self.c - self.o)
    @property
    def range(self): return self.h - self.l
    @property
    def upper(self): return self.h - max(self.o, self.c)
    @property
    def lower(self): return min(self.o, self.c) - self.l
    @property
    def bull(self): return self.c > self.o
    @property
    def bear(self): return self.c < self.o
    @property
    def mid(self): return (self.o + self.c) / 2
    @property
    def top(self): return max(self.o, self.c)
    @property
    def bot(self): return min(self.o, self.c)


def _hit(name, bias, idx):
    return {"pattern": name, "bias": bias, "index": idx[-1], "candles": list(idx)}


def detect_candlestick_patterns(o: Sequence[float], h: Sequence[float], l: Sequence[float], c: Sequence[float]) -> list[dict]:
    cs = [C(*x) for x in zip(o, h, l, c)]
    out: list[dict] = []
    for i in range(HISTORY, len(cs)):
        k, p, q = cs[i], cs[i - 1], cs[i - 2]
        r = k.range
        if r <= 0:
            continue
        avg = sum(x.body for x in cs[i - HISTORY:i]) / HISTORY
        down = cs[i - 1].c < cs[i - 6].c
        up = cs[i - 1].c > cs[i - 6].c
        is_doji = k.body <= DOJI_BODY * r

        # ---- single-candle ----
        if is_doji:
            if k.upper <= TINY_SHADOW * r and k.lower >= 0.6 * r:
                out.append(_hit("Dragonfly doji", "bullish" if down else "neutral", [i]))
            elif k.lower <= TINY_SHADOW * r and k.upper >= 0.6 * r:
                out.append(_hit("Gravestone doji", "bearish" if up else "neutral", [i]))
            elif k.upper >= 0.3 * r and k.lower >= 0.3 * r and r >= 1.5 * avg:
                out.append(_hit("Long-legged doji", "neutral", [i]))
            else:
                out.append(_hit("Doji", "neutral", [i]))
        else:
            hammer_shape = k.lower >= SHADOW_MULT * k.body and k.upper <= TINY_SHADOW * r * 1.5 and k.body <= SMALL_BODY * r
            inv_shape = k.upper >= SHADOW_MULT * k.body and k.lower <= TINY_SHADOW * r * 1.5 and k.body <= SMALL_BODY * r
            if hammer_shape and down:
                out.append(_hit("Hammer", "bullish", [i]))
            elif hammer_shape and up:
                out.append(_hit("Hanging man", "bearish", [i]))
            if inv_shape and down:
                out.append(_hit("Inverted hammer", "bullish", [i]))
            elif inv_shape and up:
                out.append(_hit("Shooting star", "bearish", [i]))
            if k.upper <= MARUBOZU_SHADOW * r and k.lower <= MARUBOZU_SHADOW * r and k.body >= LONG_BODY * avg:
                out.append(_hit("Bullish marubozu" if k.bull else "Bearish marubozu", "bullish" if k.bull else "bearish", [i]))
            if (k.body <= SMALL_BODY * r and k.upper >= k.body and k.lower >= k.body
                    and not hammer_shape and not inv_shape):
                out.append(_hit("Spinning top", "neutral", [i]))

        # ---- two-candle ----
        if p.bear and k.bull and k.o <= p.c and k.c >= p.o and k.body > p.body and down:
            out.append(_hit("Bullish engulfing", "bullish", [i - 1, i]))
        if p.bull and k.bear and k.o >= p.c and k.c <= p.o and k.body > p.body and up:
            out.append(_hit("Bearish engulfing", "bearish", [i - 1, i]))
        if p.bear and p.body >= avg and k.bull and k.top < p.o and k.bot > p.c and down:
            out.append(_hit("Bullish harami", "bullish", [i - 1, i]))
        if p.bull and p.body >= avg and k.bear and k.top < p.c and k.bot > p.o and up:
            out.append(_hit("Bearish harami", "bearish", [i - 1, i]))
        if p.bear and p.body >= avg and k.bull and k.o < p.c and p.mid < k.c < p.o and down:
            out.append(_hit("Piercing line", "bullish", [i - 1, i]))
        if p.bull and p.body >= avg and k.bear and k.o > p.c and p.o < k.c < p.mid and up:
            out.append(_hit("Dark cloud cover", "bearish", [i - 1, i]))
        if up and p.bull and k.bear and abs(k.h - p.h) <= TWEEZER_TOL * p.h:
            out.append(_hit("Tweezer top", "bearish", [i - 1, i]))
        if down and p.bear and k.bull and abs(k.l - p.l) <= TWEEZER_TOL * p.l:
            out.append(_hit("Tweezer bottom", "bullish", [i - 1, i]))

        # ---- three-candle ----
        if (q.bear and q.body >= LONG_BODY * avg and p.body <= SMALL_BODY * max(p.range, 1e-12) and p.top < q.c
                and k.bull and k.c > q.mid and cs[i - 2].c < cs[i - 7].c):
            out.append(_hit("Morning star", "bullish", [i - 2, i - 1, i]))
        if (q.bull and q.body >= LONG_BODY * avg and p.body <= SMALL_BODY * max(p.range, 1e-12) and p.bot > q.c
                and k.bear and k.c < q.mid and cs[i - 2].c > cs[i - 7].c):
            out.append(_hit("Evening star", "bearish", [i - 2, i - 1, i]))
        three = [q, p, k]
        if (all(x.bull and x.body >= 0.6 * avg and x.upper <= 0.3 * x.range for x in three)
                and q.c < p.c < k.c and q.o < p.o <= q.c and p.o < k.o <= p.c):
            out.append(_hit("Three white soldiers", "bullish", [i - 2, i - 1, i]))
        if (all(x.bear and x.body >= 0.6 * avg and x.lower <= 0.3 * x.range for x in three)
                and q.c > p.c > k.c and q.c <= p.o < q.o and p.c <= k.o < p.o):
            out.append(_hit("Three black crows", "bearish", [i - 2, i - 1, i]))
        if q.bear and q.body >= avg and p.bull and p.top < q.o and p.bot > q.c and k.bull and k.c > q.o:
            out.append(_hit("Three inside up", "bullish", [i - 2, i - 1, i]))
        if q.bull and q.body >= avg and p.bear and p.top < q.c and p.bot > q.o and k.bear and k.c < q.o:
            out.append(_hit("Three inside down", "bearish", [i - 2, i - 1, i]))
        if q.bear and p.bull and p.o <= q.c and p.c >= q.o and p.body > q.body and k.bull and k.c > p.c:
            out.append(_hit("Three outside up", "bullish", [i - 2, i - 1, i]))
        if q.bull and p.bear and p.o >= q.c and p.c <= q.o and p.body > q.body and k.bear and k.c < p.c:
            out.append(_hit("Three outside down", "bearish", [i - 2, i - 1, i]))
    return out


PATTERN_NAMES = [
    "Doji", "Dragonfly doji", "Gravestone doji", "Long-legged doji", "Hammer", "Hanging man", "Inverted hammer",
    "Shooting star", "Bullish marubozu", "Bearish marubozu", "Spinning top", "Bullish engulfing", "Bearish engulfing",
    "Bullish harami", "Bearish harami", "Piercing line", "Dark cloud cover", "Tweezer top", "Tweezer bottom",
    "Morning star", "Evening star", "Three white soldiers", "Three black crows", "Three inside up",
    "Three inside down", "Three outside up", "Three outside down",
]


# ---------------- Chart formations ----------------
def swing_points(high: Sequence[float], low: Sequence[float], k: int = 3) -> dict[str, list[int]]:
    """Fractal swings: bar i is a swing high if its high is strictly greater than the k bars on each
    side (swing low mirrored). Needs k bars AFTER i, so the latest k bars are never swings (no look-ahead)."""
    hs, ls = [], []
    for i in range(k, len(high) - k):
        if all(high[i] > high[j] for j in range(i - k, i + k + 1) if j != i):
            hs.append(i)
        if all(low[i] < low[j] for j in range(i - k, i + k + 1) if j != i):
            ls.append(i)
    return {"highs": hs, "lows": ls}


def double_tops_bottoms(high, low, close, k: int = 3, tolerance: float = 0.005, min_gap: int = 5) -> list[dict]:
    """Double top: two swing highs within `tolerance` of each other, ≥ min_gap bars apart, with a swing low
    (the neckline) between them. 'confirmed' once a later close falls below the neckline; otherwise 'forming'.
    Double bottom is the mirror image."""
    sw = swing_points(high, low, k)
    out = []
    for kind, peaks, troughs, price, opp in (("Double top", sw["highs"], sw["lows"], high, low),
                                             ("Double bottom", sw["lows"], sw["highs"], low, high)):
        for a, b in zip(peaks, peaks[1:]):
            if b - a < min_gap or abs(price[a] - price[b]) > tolerance * price[a]:
                continue
            between = [t for t in troughs if a < t < b]
            if not between:
                continue
            neck_i = (min if kind == "Double top" else max)(between, key=lambda t: opp[t])
            neck = opp[neck_i]
            after = range(b + 1, len(close))
            conf = next((j for j in after if (close[j] < neck if kind == "Double top" else close[j] > neck)), None)
            out.append({"formation": kind, "bias": "bearish" if kind == "Double top" else "bullish",
                        "points": [a, neck_i, b], "neckline": neck, "status": "confirmed" if conf is not None else "forming",
                        "confirmed_index": conf})
    return out
