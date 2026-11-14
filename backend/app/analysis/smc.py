"""Smart Money Concepts — explicit, deterministic rules.

These are ALGORITHMIC interpretations of price action. They do not prove institutional activity.
Timing: a fractal swing at bar s (k bars each side) is only KNOWN at bar s+k. Every event below
uses only swings already confirmed at the bar being processed — no look-ahead.

Definitions
- Structure: walking forward, keep the latest confirmed, unbroken swing high (SH) and swing low (SL).
  A CLOSE above SH is a bullish break; below SL a bearish break. It is a CHOCH (change of character,
  also called MSS) if it reverses the current structure direction, otherwise a BOS (break of structure).
  The first break has no prior direction and is reported as BOS.
- Order block (OB): for a bullish break, the last bearish candle (C<O) between the broken swing and the
  break bar; zone = that candle's [low, high]. Mirror for bearish. Status: "fresh" until price trades back
  into the zone ("mitigated"); "broken" once a close goes through the far side.
- Fair value gap (FVG): bullish when low[i] > high[i−2] (gap = [high[i−2], low[i]]), bearish when
  high[i] < low[i−2]. Must be ≥ min_fvg_atr × ATR14 at that bar. Status: open → partial (price enters) →
  filled (price trades through the whole gap).
- Liquidity: unbroken swing highs are buy-side liquidity (BSL), swing lows sell-side liquidity (SSL).
  A sweep is a bar whose wick goes beyond the level but whose close is back inside; the level is then spent.
  Two swing highs/lows within eq_tol are flagged "equal highs/lows".
- Premium/discount: dealing range = latest confirmed swing high and swing low; equilibrium = midpoint.
  Above equilibrium = premium, below = discount.
- Inducement: after a bullish break, the first minor swing low (1-bar fractal) that forms above the active
  bullish OB; "taken" when a later low trades below it. Mirror for bearish.
"""
from __future__ import annotations

from .indicators import atr
from .patterns import swing_points


def _minor_swings(high, low):
    return swing_points(high, low, 1)


def structure(o, h, l, c, k: int = 3) -> list[dict]:
    sw = swing_points(h, l, k)
    highs = sorted(sw["highs"])
    lows = sorted(sw["lows"])
    events, trend = [], None
    sh = sl = None  # (index, level, broken)
    hi_ptr = lo_ptr = 0
    for j in range(len(c)):
        # admit swings confirmed by bar j (swing s confirmed at s+k)
        while hi_ptr < len(highs) and highs[hi_ptr] + k <= j:
            sh = [highs[hi_ptr], h[highs[hi_ptr]], False]
            hi_ptr += 1
        while lo_ptr < len(lows) and lows[lo_ptr] + k <= j:
            sl = [lows[lo_ptr], l[lows[lo_ptr]], False]
            lo_ptr += 1
        if sh and not sh[2] and c[j] > sh[1]:
            kind = "CHOCH" if trend == "bearish" else "BOS"
            events.append({"type": kind, "direction": "bullish", "level": sh[1], "swing_index": sh[0], "index": j})
            sh[2], trend = True, "bullish"
        elif sl and not sl[2] and c[j] < sl[1]:
            kind = "CHOCH" if trend == "bullish" else "BOS"
            events.append({"type": kind, "direction": "bearish", "level": sl[1], "swing_index": sl[0], "index": j})
            sl[2], trend = True, "bearish"
    return events


def order_blocks(o, h, l, c, events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        b, s = e["index"], e["swing_index"]
        bull = e["direction"] == "bullish"
        cand = [i for i in range(s, b) if (c[i] < o[i] if bull else c[i] > o[i])]
        if not cand:
            continue
        i = cand[-1]
        lo, hi = l[i], h[i]
        status, mitigated, broken = "fresh", None, None
        for j in range(b + 1, len(c)):
            if bull:
                if c[j] < lo:
                    status, broken = "broken", j
                    break
                if mitigated is None and l[j] <= hi:
                    status, mitigated = "mitigated", j
            else:
                if c[j] > hi:
                    status, broken = "broken", j
                    break
                if mitigated is None and h[j] >= lo:
                    status, mitigated = "mitigated", j
        out.append({"direction": e["direction"], "index": i, "low": lo, "high": hi, "created_index": b,
                    "status": status, "mitigated_index": mitigated, "broken_index": broken, "from_event": e["type"]})
    return out


def fair_value_gaps(h, l, c, min_fvg_atr: float = 0.1) -> list[dict]:
    a = atr(h, l, c, 14)
    out = []
    for i in range(2, len(c)):
        if a[i] is None:
            continue
        for bull in (True, False):
            lo, hi = (h[i - 2], l[i]) if bull else (h[i], l[i - 2])
            if hi - lo <= 0 or hi - lo < min_fvg_atr * a[i]:
                continue
            status, touched, filled = "open", None, None
            for j in range(i + 1, len(c)):
                if bull:
                    if l[j] <= lo:
                        status, filled = "filled", j
                        break
                    if touched is None and l[j] <= hi:
                        status, touched = "partial", j
                else:
                    if h[j] >= hi:
                        status, filled = "filled", j
                        break
                    if touched is None and h[j] >= lo:
                        status, touched = "partial", j
            out.append({"direction": "bullish" if bull else "bearish", "index": i - 1, "low": lo, "high": hi,
                        "status": status, "touched_index": touched, "filled_index": filled})
    return out


def liquidity(h, l, c, k: int = 3, eq_tol: float = 0.001) -> dict:
    sw = swing_points(h, l, k)
    levels = []
    for side, idxs, price in (("BSL", sw["highs"], h), ("SSL", sw["lows"], l)):
        for s in idxs:
            lvl = price[s]
            swept = None
            for j in range(s + k + 1, len(c)):     # only after the swing is confirmed
                if side == "BSL" and h[j] > lvl:
                    swept = j if c[j] < lvl else None
                    levels.append({"side": side, "index": s, "level": lvl, "status": "swept" if swept is not None else "taken", "event_index": j})
                    break
                if side == "SSL" and l[j] < lvl:
                    swept = j if c[j] > lvl else None
                    levels.append({"side": side, "index": s, "level": lvl, "status": "swept" if swept is not None else "taken", "event_index": j})
                    break
            else:
                levels.append({"side": side, "index": s, "level": lvl, "status": "resting", "event_index": None})
    for x in levels:
        x["equal"] = any(y is not x and y["side"] == x["side"] and abs(y["level"] - x["level"]) <= eq_tol * x["level"] for y in levels)
    levels.sort(key=lambda x: (x["index"], x["side"]))
    return {"levels": levels, "sweeps": [x for x in levels if x["status"] == "swept"]}


def premium_discount(h, l, c, k: int = 3) -> dict | None:
    sw = swing_points(h, l, k)
    if not sw["highs"] or not sw["lows"]:
        return None
    hi_i, lo_i = sw["highs"][-1], sw["lows"][-1]
    hi, lo = h[hi_i], l[lo_i]
    if hi <= lo:
        return None
    eq = (hi + lo) / 2
    px = c[-1]
    zone = "premium" if px > eq else "discount" if px < eq else "equilibrium"
    return {"range_high": hi, "range_low": lo, "equilibrium": eq, "zone": zone, "position": (px - lo) / (hi - lo),
            "high_index": hi_i, "low_index": lo_i}


def inducements(h, l, c, events, obs) -> list[dict]:
    minor = _minor_swings(h, l)
    out = []
    for e in events:
        ob = next((x for x in obs if x["created_index"] == e["index"]), None)
        if ob is None:
            continue
        bull = e["direction"] == "bullish"
        pts = minor["lows"] if bull else minor["highs"]
        cand = next((p for p in pts if p > e["index"] and (l[p] > ob["high"] if bull else h[p] < ob["low"])), None)
        if cand is None:
            continue
        lvl = l[cand] if bull else h[cand]
        taken = next((j for j in range(cand + 2, len(c)) if (l[j] < lvl if bull else h[j] > lvl)), None)
        out.append({"direction": e["direction"], "index": cand, "level": lvl, "taken_index": taken,
                    "status": "taken" if taken is not None else "untaken", "event_index": e["index"]})
    return out


def analyze_smc(o, h, l, c, k: int = 3) -> dict:
    ev = structure(o, h, l, c, k)
    obs = order_blocks(o, h, l, c, ev)
    return {"structure": ev, "trend": ev[-1]["direction"] if ev else None, "order_blocks": obs,
            "fvgs": fair_value_gaps(h, l, c), "liquidity": liquidity(h, l, c, k),
            "premium_discount": premium_discount(h, l, c, k), "inducements": inducements(h, l, c, ev, obs)}
