"""Candlestick patterns and formations on hand-built candles."""
from app.analysis.patterns import PATTERN_NAMES, detect_candlestick_patterns, double_tops_bottoms, swing_points


def series(pre, extra):
    """`pre`: list of (o,h,l,c) setting up context (≥ 10 bars), then the pattern candles."""
    rows = pre + extra
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]


def downtrend(n=12, start=120.0):
    out, p = [], start
    for _ in range(n):
        out.append((p, p + 0.3, p - 2.2, p - 2.0)); p -= 2.0
    return out


def uptrend(n=12, start=80.0):
    out, p = [], start
    for _ in range(n):
        out.append((p, p + 2.2, p - 0.3, p + 2.0)); p += 2.0
    return out


def names(o, h, l, c, at=None):
    hits = detect_candlestick_patterns(o, h, l, c)
    at = len(o) - 1 if at is None else at
    return {x["pattern"] for x in hits if x["index"] == at}


def test_hammer_after_downtrend_and_hanging_man_after_uptrend():
    d = downtrend(); last = d[-1][3]
    assert "Hammer" in names(*series(d, [(last, last + 0.05, last - 3.0, last + 0.4)]))
    u = uptrend(); last = u[-1][3]
    assert "Hanging man" in names(*series(u, [(last, last + 0.05, last - 3.0, last + 0.4)]))


def test_shooting_star_and_inverted_hammer():
    u = uptrend(); last = u[-1][3]
    assert "Shooting star" in names(*series(u, [(last, last + 3.0, last - 0.05, last - 0.4)]))
    d = downtrend(); last = d[-1][3]
    assert "Inverted hammer" in names(*series(d, [(last, last + 3.0, last - 0.05, last + 0.4)]))


def test_doji_family():
    d = downtrend(); x = d[-1][3]
    assert "Dragonfly doji" in names(*series(d, [(x, x + 0.01, x - 3, x)]))
    u = uptrend(); x = u[-1][3]
    assert "Gravestone doji" in names(*series(u, [(x, x + 3, x - 0.01, x)]))
    assert "Long-legged doji" in names(*series(u, [(x, x + 2, x - 2, x)]))


def test_engulfing():
    d = downtrend(); x = d[-1][3]
    assert "Bullish engulfing" in names(*series(d, [(x, x + 0.1, x - 1.2, x - 1.0), (x - 1.1, x + 0.6, x - 1.2, x + 0.5)]))
    u = uptrend(); x = u[-1][3]
    assert "Bearish engulfing" in names(*series(u, [(x, x + 1.2, x - 0.1, x + 1.0), (x + 1.1, x + 1.2, x - 0.6, x - 0.5)]))


def test_morning_and_evening_star():
    d = downtrend(); x = d[-1][3]
    assert "Morning star" in names(*series(d, [(x, x + 0.1, x - 4.1, x - 4.0), (x - 4.5, x - 4.2, x - 4.9, x - 4.4), (x - 4.2, x - 1.0, x - 4.3, x - 1.2)]))
    u = uptrend(); x = u[-1][3]
    assert "Evening star" in names(*series(u, [(x, x + 4.1, x - 0.1, x + 4.0), (x + 4.5, x + 4.9, x + 4.2, x + 4.6), (x + 4.2, x + 4.3, x + 1.0, x + 1.2)]))


def test_three_soldiers_and_crows():
    flat = [(100, 100.6, 99.4, 100 + (0.2 if i % 2 else -0.2)) for i in range(12)]
    assert "Three white soldiers" in names(*series(flat, [(100, 101.6, 99.9, 101.5), (101.0, 102.6, 100.9, 102.5), (102.0, 103.6, 101.9, 103.5)]))
    assert "Three black crows" in names(*series(flat, [(100, 100.1, 98.4, 98.5), (99.0, 99.1, 97.4, 97.5), (98.0, 98.1, 96.4, 96.5)]))


def test_marubozu():
    flat = [(100, 100.6, 99.4, 100 + (0.2 if i % 2 else -0.2)) for i in range(12)]
    assert "Bullish marubozu" in names(*series(flat, [(100, 102.0, 100.0, 102.0)]))
    assert "Bearish marubozu" in names(*series(flat, [(100, 100.0, 98.0, 98.0)]))


def test_hits_name_their_candles_and_are_known():
    d = downtrend(); x = d[-1][3]
    hits = detect_candlestick_patterns(*series(d, [(x, x + 0.1, x - 1.2, x - 1.0), (x - 1.1, x + 0.6, x - 1.2, x + 0.5)]))
    eng = next(h for h in hits if h["pattern"] == "Bullish engulfing")
    assert eng["candles"] == [len(d), len(d) + 1] and eng["bias"] == "bullish"
    assert all(h["pattern"] in PATTERN_NAMES for h in hits)


def test_no_pattern_without_history():
    assert detect_candlestick_patterns([1, 1], [2, 2], [0, 0], [1, 1]) == []


def test_swing_points_and_double_top():
    # peaks at 5 and 15 (equal), trough at 10, then a break below the neckline
    hs = [1, 2, 3, 4, 5, 10, 5, 4, 3, 4, 2, 4, 3, 4, 5, 10.02, 5, 4, 3, 2, 1, 1, 1]
    ls = [x - 0.5 for x in hs]
    cs = [x - 0.25 for x in hs]
    sw = swing_points(hs, ls, 3)
    assert 5 in sw["highs"] and 15 in sw["highs"] and 10 in sw["lows"]
    f = [x for x in double_tops_bottoms(hs, ls, cs) if x["formation"] == "Double top"][0]
    assert f["points"] == [5, 10, 15] and f["neckline"] == 1.5 and f["status"] == "confirmed" and f["confirmed_index"] == 20


def test_swings_never_use_last_k_bars():
    hs = list(range(20)) + [100]
    assert 20 not in swing_points(hs, hs, 3)["highs"]


def scenario_series():
    """Hand-built scenarios that trigger every pattern; also reused by the parity test."""
    d, u = downtrend(), uptrend()
    xd, xu = d[-1][3], u[-1][3]
    flat = [(100, 100.6, 99.4, 100 + (0.2 if i % 2 else -0.2)) for i in range(12)]
    return {
        "Hammer": d + [(xd, xd + 0.05, xd - 3.0, xd + 0.4)],
        "Hanging man": u + [(xu, xu + 0.05, xu - 3.0, xu + 0.4)],
        "Shooting star": u + [(xu, xu + 3.0, xu - 0.05, xu - 0.4)],
        "Inverted hammer": d + [(xd, xd + 3.0, xd - 0.05, xd + 0.4)],
        "Dragonfly doji": d + [(xd, xd + 0.01, xd - 3, xd)],
        "Gravestone doji": u + [(xu, xu + 3, xu - 0.01, xu)],
        "Long-legged doji": u + [(xu, xu + 2, xu - 2, xu)],
        "Doji": flat + [(100, 100.3, 99.9, 100.01)],
        "Spinning top": flat + [(100, 100.5, 99.5, 100.2)],
        "Bullish marubozu": flat + [(100, 102.0, 100.0, 102.0)],
        "Bearish marubozu": flat + [(100, 100.0, 98.0, 98.0)],
        "Bullish engulfing": d + [(xd, xd + 0.1, xd - 1.2, xd - 1.0), (xd - 1.1, xd + 0.6, xd - 1.2, xd + 0.5)],
        "Bearish engulfing": u + [(xu, xu + 1.2, xu - 0.1, xu + 1.0), (xu + 1.1, xu + 1.2, xu - 0.6, xu - 0.5)],
        "Bullish harami": d + [(xd, xd + 0.1, xd - 4.1, xd - 4.0), (xd - 3.0, xd - 2.4, xd - 3.1, xd - 2.5)],
        "Bearish harami": u + [(xu, xu + 4.1, xu - 0.1, xu + 4.0), (xu + 3.0, xu + 3.1, xu + 2.4, xu + 2.5)],
        "Piercing line": d + [(xd, xd + 0.1, xd - 4.1, xd - 4.0), (xd - 4.5, xd - 1.0, xd - 4.6, xd - 1.5)],
        "Dark cloud cover": u + [(xu, xu + 4.1, xu - 0.1, xu + 4.0), (xu + 4.5, xu + 4.6, xu + 1.0, xu + 1.5)],
        "Tweezer top": u + [(xu, xu + 1.5, xu - 0.1, xu + 1.2), (xu + 1.2, xu + 1.5, xu + 0.2, xu + 0.4)],
        "Tweezer bottom": d + [(xd, xd + 0.1, xd - 1.5, xd - 1.2), (xd - 1.2, xd - 0.2, xd - 1.5, xd - 0.4)],
        "Morning star": d + [(xd, xd + 0.1, xd - 4.1, xd - 4.0), (xd - 4.5, xd - 4.2, xd - 4.9, xd - 4.4), (xd - 4.2, xd - 1.0, xd - 4.3, xd - 1.2)],
        "Evening star": u + [(xu, xu + 4.1, xu - 0.1, xu + 4.0), (xu + 4.5, xu + 4.9, xu + 4.2, xu + 4.6), (xu + 4.2, xu + 4.3, xu + 1.0, xu + 1.2)],
        "Three white soldiers": flat + [(100, 101.6, 99.9, 101.5), (101.0, 102.6, 100.9, 102.5), (102.0, 103.6, 101.9, 103.5)],
        "Three black crows": flat + [(100, 100.1, 98.4, 98.5), (99.0, 99.1, 97.4, 97.5), (98.0, 98.1, 96.4, 96.5)],
        "Three inside up": flat + [(100, 100.1, 97.9, 98.0), (98.5, 99.6, 98.4, 99.5), (99.5, 100.6, 99.4, 100.5)],
        "Three inside down": flat + [(100, 102.1, 99.9, 102.0), (101.5, 101.6, 100.4, 100.5), (100.5, 100.6, 99.4, 99.5)],
        "Three outside up": flat + [(100, 100.1, 99.4, 99.5), (99.4, 100.8, 99.3, 100.7), (100.7, 101.5, 100.6, 101.4)],
        "Three outside down": flat + [(100, 100.6, 99.9, 100.5), (100.6, 100.7, 99.2, 99.3), (99.3, 99.4, 98.5, 98.6)],
    }


def test_every_pattern_has_a_triggering_scenario():
    sc = scenario_series()
    assert set(sc) == set(PATTERN_NAMES)
    for name, rows in sc.items():
        assert name in names(*series([], rows)), name
