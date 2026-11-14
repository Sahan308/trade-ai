"""Indicators. Conventions:
* Inputs are equal-length lists ordered oldest → newest.
* Outputs are lists of the same length; positions inside the warm-up period are None.
* No look-ahead: value[i] uses data up to and including i only (Ichimoku spans/chikou are
  the documented exceptions and are aligned as described in their docstring).
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Num = float | None


def _none(n: int) -> list[Num]:
    return [None] * n


# ---------------- Moving averages ----------------
def sma(x: Sequence[float], n: int) -> list[Num]:
    """Simple MA: mean of the last n values."""
    out, s = _none(len(x)), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x: Sequence[Num], n: int) -> list[Num]:
    """Exponential MA, alpha = 2/(n+1), seeded with the SMA of the first n valid values.
    Leading None values (e.g. another indicator's warm-up) are skipped."""
    out = _none(len(x))
    a = 2 / (n + 1)
    start = next((i for i, v in enumerate(x) if v is not None), None)
    if start is None or len(x) - start < n:
        return out
    prev = sum(x[start:start + n]) / n
    out[start + n - 1] = prev
    for i in range(start + n, len(x)):
        prev = a * x[i] + (1 - a) * prev
        out[i] = prev
    return out


def wma(x: Sequence[float], n: int) -> list[Num]:
    """Linearly weighted MA: weights 1..n, newest heaviest."""
    out, d = _none(len(x)), n * (n + 1) / 2
    for i in range(n - 1, len(x)):
        out[i] = sum(x[i - n + 1 + k] * (k + 1) for k in range(n)) / d
    return out


def vwma(close: Sequence[float], volume: Sequence[float], n: int) -> list[Num]:
    """Volume-weighted MA: Σ(close·volume)/Σ(volume) over n bars (None when Σvolume = 0)."""
    out = _none(len(close))
    for i in range(n - 1, len(close)):
        v = sum(volume[i - n + 1:i + 1])
        out[i] = sum(c * w for c, w in zip(close[i - n + 1:i + 1], volume[i - n + 1:i + 1])) / v if v else None
    return out


def _wilder(x: Sequence[float], n: int, first: int = 0) -> list[Num]:
    """Wilder smoothing (RMA): seed = mean of x[first:first+n], then (prev·(n-1) + x)/n."""
    out = _none(len(x))
    if len(x) - first < n:
        return out
    prev = sum(x[first:first + n]) / n
    out[first + n - 1] = prev
    for i in range(first + n, len(x)):
        prev = (prev * (n - 1) + x[i]) / n
        out[i] = prev
    return out


# ---------------- Momentum ----------------
def rsi(close: Sequence[float], n: int = 14) -> list[Num]:
    """Wilder RSI. 100 − 100/(1 + avgGain/avgLoss); 100 if avgLoss = 0 (50 if both are 0)."""
    out = _none(len(close))
    if len(close) <= n:
        return out
    gains = [0.0] + [max(close[i] - close[i - 1], 0.0) for i in range(1, len(close))]
    losses = [0.0] + [max(close[i - 1] - close[i], 0.0) for i in range(1, len(close))]
    ag, al = _wilder(gains, n, 1), _wilder(losses, n, 1)
    for i in range(n, len(close)):
        g, l = ag[i], al[i]
        out[i] = 50.0 if g == 0 and l == 0 else 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def macd(close: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[Num]]:
    """MACD = EMA(fast) − EMA(slow); signal = EMA(signal) of MACD; histogram = MACD − signal."""
    f, s = ema(close, fast), ema(close, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    sig = ema(line, signal)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return {"macd": line, "signal": sig, "histogram": hist}


def stochastic(high, low, close, k: int = 14, smooth_k: int = 3, d: int = 3) -> dict[str, list[Num]]:
    """Slow stochastic: raw %K = 100·(C − LL_k)/(HH_k − LL_k) (50 if range is 0);
    %K = SMA(raw, smooth_k); %D = SMA(%K, d)."""
    raw = _none(len(close))
    for i in range(k - 1, len(close)):
        hh, ll = max(high[i - k + 1:i + 1]), min(low[i - k + 1:i + 1])
        raw[i] = 50.0 if hh == ll else 100 * (close[i] - ll) / (hh - ll)
    kk = _sma_skip(raw, smooth_k)
    return {"k": kk, "d": _sma_skip(kk, d)}


def _sma_skip(x: Sequence[Num], n: int) -> list[Num]:
    out = _none(len(x))
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if all(v is not None for v in w):
            out[i] = sum(w) / n
    return out


def cci(high, low, close, n: int = 20) -> list[Num]:
    """Commodity Channel Index: (TP − SMA(TP))/(0.015 · mean absolute deviation), TP = (H+L+C)/3."""
    tp = [(h + l + c) / 3 for h, l, c in zip(high, low, close)]
    m, out = sma(tp, n), _none(len(tp))
    for i in range(n - 1, len(tp)):
        md = sum(abs(v - m[i]) for v in tp[i - n + 1:i + 1]) / n
        out[i] = 0.0 if md == 0 else (tp[i] - m[i]) / (0.015 * md)
    return out


def mfi(high, low, close, volume, n: int = 14) -> list[Num]:
    """Money Flow Index: TP·volume split by TP rising/falling; 100 − 100/(1 + pos/neg); 100 if neg = 0."""
    tp = [(h + l + c) / 3 for h, l, c in zip(high, low, close)]
    out = _none(len(tp))
    for i in range(n, len(tp)):
        pos = neg = 0.0
        for j in range(i - n + 1, i + 1):
            flow = tp[j] * volume[j]
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        out[i] = 50.0 if pos == 0 and neg == 0 else 100.0 if neg == 0 else 100 - 100 / (1 + pos / neg)
    return out


# ---------------- Volatility ----------------
def true_range(high, low, close) -> list[float]:
    """TR = max(H−L, |H−C₋₁|, |L−C₋₁|); first bar uses H−L."""
    return [high[0] - low[0]] + [max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
                                 for i in range(1, len(close))]


def atr(high, low, close, n: int = 14) -> list[Num]:
    """Average True Range with Wilder smoothing."""
    return _wilder(true_range(high, low, close), n) if close else []


def bollinger(close, n: int = 20, k: float = 2.0) -> dict[str, list[Num]]:
    """Middle = SMA(n); bands = middle ± k·σ (population standard deviation over n)."""
    mid, up, lo = sma(close, n), _none(len(close)), _none(len(close))
    for i in range(n - 1, len(close)):
        sd = math.sqrt(sum((v - mid[i]) ** 2 for v in close[i - n + 1:i + 1]) / n)
        up[i], lo[i] = mid[i] + k * sd, mid[i] - k * sd
    return {"middle": mid, "upper": up, "lower": lo}


def keltner(high, low, close, n: int = 20, mult: float = 2.0, atr_n: int = 10) -> dict[str, list[Num]]:
    """Middle = EMA(n); bands = middle ± mult·ATR(atr_n)."""
    mid, a = ema(close, n), atr(high, low, close, atr_n)
    up = [m + mult * x if m is not None and x is not None else None for m, x in zip(mid, a)]
    lo = [m - mult * x if m is not None and x is not None else None for m, x in zip(mid, a)]
    return {"middle": mid, "upper": up, "lower": lo}


# ---------------- Trend ----------------
def adx(high, low, close, n: int = 14) -> dict[str, list[Num]]:
    """Wilder DMI/ADX. +DM/−DM per Wilder; smoothed with Wilder sums; DX = 100·|+DI−−DI|/(+DI+−DI);
    ADX = Wilder average of DX (first value at index 2n−1)."""
    L = len(close)
    plus_di, minus_di, adx_out = _none(L), _none(L), _none(L)
    if L <= 2 * n:
        return {"plus_di": plus_di, "minus_di": minus_di, "adx": adx_out}
    tr = true_range(high, low, close)
    pdm, mdm = [0.0] * L, [0.0] * L
    for i in range(1, L):
        up, dn = high[i] - high[i - 1], low[i - 1] - low[i]
        pdm[i] = up if up > dn and up > 0 else 0.0
        mdm[i] = dn if dn > up and dn > 0 else 0.0
    s_tr, s_p, s_m = sum(tr[1:n + 1]), sum(pdm[1:n + 1]), sum(mdm[1:n + 1])
    dx = _none(L)
    for i in range(n, L):
        if i > n:
            s_tr, s_p, s_m = s_tr - s_tr / n + tr[i], s_p - s_p / n + pdm[i], s_m - s_m / n + mdm[i]
        p, m = (100 * s_p / s_tr, 100 * s_m / s_tr) if s_tr else (0.0, 0.0)
        plus_di[i], minus_di[i] = p, m
        dx[i] = 0.0 if p + m == 0 else 100 * abs(p - m) / (p + m)
    prev = sum(dx[n:2 * n]) / n
    adx_out[2 * n - 1] = prev
    for i in range(2 * n, L):
        prev = (prev * (n - 1) + dx[i]) / n
        adx_out[i] = prev
    return {"plus_di": plus_di, "minus_di": minus_di, "adx": adx_out}


def supertrend(high, low, close, n: int = 10, mult: float = 3.0) -> dict[str, list]:
    """Supertrend on ATR(n): basic bands = (H+L)/2 ± mult·ATR; final bands only tighten while price
    stays inside; direction flips when close crosses the opposite final band. direction: 1 up, −1 down."""
    L = len(close)
    a = atr(high, low, close, n)
    line, direction = _none(L), [None] * L
    fu = fl = None
    d = 1
    for i in range(L):
        if a[i] is None:
            continue
        hl2 = (high[i] + low[i]) / 2
        bu, bl = hl2 + mult * a[i], hl2 - mult * a[i]
        if fu is None:
            fu, fl = bu, bl
            d = 1 if close[i] >= hl2 else -1
        else:
            fu = bu if (bu < fu or close[i - 1] > fu) else fu
            fl = bl if (bl > fl or close[i - 1] < fl) else fl
            if d == 1 and close[i] < fl:
                d = -1
            elif d == -1 and close[i] > fu:
                d = 1
        line[i], direction[i] = (fl if d == 1 else fu), d
    return {"supertrend": line, "direction": direction}


def ichimoku(high, low, close, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, shift: int = 26) -> dict[str, list[Num]]:
    """Ichimoku. tenkan/kijun = midpoint of HH/LL over 9/26. Span A = (tenkan+kijun)/2 and
    Span B = midpoint over 52 are plotted `shift` bars ahead: here span_a[i]/span_b[i] are the cloud
    values AT bar i (i.e. computed at i−shift) — no look-ahead. chikou[i] = close[i] plotted shift bars
    back; it is returned as chikou[i−shift] = close[i], so the last `shift` positions are None."""
    L = len(close)

    def mid(p, i):
        return (max(high[i - p + 1:i + 1]) + min(low[i - p + 1:i + 1])) / 2 if i >= p - 1 else None

    t = [mid(tenkan, i) for i in range(L)]
    k = [mid(kijun, i) for i in range(L)]
    raw_a = [(a + b) / 2 if a is not None and b is not None else None for a, b in zip(t, k)]
    raw_b = [mid(senkou_b, i) for i in range(L)]
    span_a = [raw_a[i - shift] if i >= shift else None for i in range(L)]
    span_b = [raw_b[i - shift] if i >= shift else None for i in range(L)]
    chikou = [close[i + shift] if i + shift < L else None for i in range(L)]
    return {"tenkan": t, "kijun": k, "span_a": span_a, "span_b": span_b, "chikou": chikou}


def parabolic_sar(high, low, step: float = 0.02, max_step: float = 0.2) -> list[Num]:
    """Wilder Parabolic SAR. Starts long if bar 1 closes higher high than bar 0, else short.
    SAR never moves inside the prior two bars' range; reverses when price crosses it."""
    L = len(high)
    out = _none(L)
    if L < 2:
        return out
    up = high[1] >= high[0]
    sar = low[0] if up else high[0]
    ep = high[1] if up else low[1]
    af = step
    for i in range(1, L):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if low[i] < sar:
                up, sar, ep, af = False, ep, low[i], step
            elif high[i] > ep:
                ep, af = high[i], min(af + step, max_step)
        else:
            sar = max(sar, high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if high[i] > sar:
                up, sar, ep, af = True, ep, high[i], step
            elif low[i] < ep:
                ep, af = low[i], min(af + step, max_step)
        out[i] = sar
    return out


# ---------------- Volume ----------------
def obv(close, volume) -> list[float]:
    """On-Balance Volume, starting at 0."""
    out, s = [0.0] * len(close), 0.0
    for i in range(1, len(close)):
        s += volume[i] if close[i] > close[i - 1] else -volume[i] if close[i] < close[i - 1] else 0.0
        out[i] = s
    return out


def vwap(time_ms, high, low, close, volume) -> list[Num]:
    """Session VWAP anchored to each UTC day: Σ(TP·V)/ΣV since 00:00 UTC (None if ΣV = 0)."""
    out, pv, vv, day = _none(len(close)), 0.0, 0.0, None
    for i, t in enumerate(time_ms):
        d = int(t // 86_400_000)
        if d != day:
            day, pv, vv = d, 0.0, 0.0
        pv += (high[i] + low[i] + close[i]) / 3 * volume[i]
        vv += volume[i]
        out[i] = pv / vv if vv else None
    return out


def volume_profile(high, low, close, volume, bins: int = 24, value_area: float = 0.7) -> dict:
    """Volume by price: each bar's volume goes to the bin containing its typical price.
    POC = highest-volume bin; value area grows from the POC to cover `value_area` of volume."""
    if not close:
        return {"bins": [], "poc": None, "value_area_high": None, "value_area_low": None}
    lo, hi = min(low), max(high)
    width = (hi - lo) / bins if hi > lo else 1.0
    vols = [0.0] * bins
    for h, l, c, v in zip(high, low, close, volume):
        idx = min(bins - 1, int(((h + l + c) / 3 - lo) / width)) if hi > lo else 0
        vols[idx] += v
    poc = max(range(bins), key=lambda b: vols[b])
    total, inside, a, b = sum(vols), vols[poc], poc, poc
    while total and inside / total < value_area and (a > 0 or b < bins - 1):
        below = vols[a - 1] if a > 0 else -1
        above = vols[b + 1] if b < bins - 1 else -1
        if above >= below:
            b += 1
            inside += vols[b]
        else:
            a -= 1
            inside += vols[a]
    edges = [(lo + i * width, lo + (i + 1) * width) for i in range(bins)]
    return {"bins": [{"low": e[0], "high": e[1], "volume": v} for e, v in zip(edges, vols)],
            "poc": (edges[poc][0] + edges[poc][1]) / 2, "value_area_low": edges[a][0], "value_area_high": edges[b][1]}


# ---------------- Levels ----------------
FIB_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def fibonacci(high, low, lookback: int = 100) -> dict | None:
    """Retracement levels between the highest high and lowest low of the last `lookback` bars.
    If the high came after the low (up-move), levels are measured down from the high; otherwise up from the low."""
    if not high:
        return None
    s = max(0, len(high) - lookback)
    hi_i = max(range(s, len(high)), key=lambda i: high[i])
    lo_i = min(range(s, len(low)), key=lambda i: low[i])
    hi, lo = high[hi_i], low[lo_i]
    up = hi_i > lo_i
    levels = {f"{r:g}": (hi - r * (hi - lo)) if up else (lo + r * (hi - lo)) for r in FIB_RATIOS}
    return {"direction": "up" if up else "down", "swing_high": hi, "swing_low": lo,
            "swing_high_index": hi_i, "swing_low_index": lo_i, "levels": levels}


def pivots(time_ms, high, low, close, interval_ms: int) -> dict | None:
    """Classic floor pivots from the previous completed UTC day (or the previous bar for ≥1D charts).
    P=(H+L+C)/3, R1=2P−L, S1=2P−H, R2=P+(H−L), S2=P−(H−L), R3=H+2(P−L), S3=L−2(H−P)."""
    if len(close) < 2:
        return None
    if interval_ms >= 86_400_000:
        h, l, c = high[-2], low[-2], close[-2]
        basis = "previous bar"
    else:
        today = int(time_ms[-1] // 86_400_000)
        idx = [i for i, t in enumerate(time_ms) if int(t // 86_400_000) == today - 1]
        if not idx:
            return None
        h, l, c = max(high[i] for i in idx), min(low[i] for i in idx), close[idx[-1]]
        basis = "previous UTC day"
    p = (h + l + c) / 3
    return {"basis": basis, "p": p, "r1": 2 * p - l, "s1": 2 * p - h, "r2": p + (h - l), "s2": p - (h - l),
            "r3": h + 2 * (p - l), "s3": l - 2 * (h - p)}
