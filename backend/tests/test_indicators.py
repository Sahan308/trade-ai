"""Indicator correctness: hand-computed values, warm-up handling and edge cases."""
import math

import pytest

from app.analysis import indicators as ind
from tests.fixtures import H, T0, candles

approx = lambda x: pytest.approx(x, rel=1e-9, abs=1e-9)  # noqa: E731


def test_sma_wma_hand_values():
    x = [1, 2, 3, 4, 5]
    assert ind.sma(x, 3) == [None, None, 2, 3, 4]
    assert ind.wma(x, 3) == [None, None, approx((1 + 4 + 9) / 6), approx((2 + 6 + 12) / 6), approx((3 + 8 + 15) / 6)]


def test_ema_seeded_with_sma_and_skips_leading_none():
    assert ind.ema([2, 4, 6, 8], 3) == [None, None, 4, approx(0.5 * 8 + 0.5 * 4)]
    assert ind.ema([None, None, 2, 4, 6, 8], 3) == [None, None, None, None, 4, 6]


def test_vwma():
    assert ind.vwma([10, 20], [1, 3], 2) == [None, approx((10 + 60) / 4)]
    assert ind.vwma([10, 20], [0, 0], 2) == [None, None]


def test_rsi_known_cases():
    up = list(range(1, 30))
    assert ind.rsi(up, 14)[-1] == 100.0
    assert ind.rsi([5] * 20, 14)[-1] == 50.0
    r = ind.rsi(up, 14)
    assert r[13] is None and r[14] is not None            # warm-up: first value at index n
    # alternating +1/-1: avg gain = avg loss → 50
    alt = [10 + (i % 2) for i in range(40)]
    assert 45 < ind.rsi(alt)[-1] < 55


def test_rsi_wilder_reference():
    # Widely used Wilder example. Over the 14 changes, gains sum to 3.34 and losses to 1.40, so the
    # first RSI is 100 − 100/(1 + 3.34/1.40) ≈ 70.46 (published tables show 70.53 from rounded averages).
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    assert ind.rsi(closes, 14)[14] == pytest.approx(100 - 100 / (1 + 3.34 / 1.40), abs=1e-9)


def test_true_range_and_atr():
    h, l, c = [10, 12, 11], [8, 9, 7], [9, 11, 8]
    assert ind.true_range(h, l, c) == [2, 3, 4]
    assert ind.atr(h, l, c, 2) == [None, 2.5, approx((2.5 + 4) / 2)]


def test_bollinger_flat_series_has_zero_width():
    b = ind.bollinger([5.0] * 25, 20, 2)
    assert b["upper"][-1] == b["lower"][-1] == b["middle"][-1] == 5.0


def test_macd_structure_and_warmup():
    _, _, _, _, c, _ = candles(120)
    m = ind.macd(c)
    first_line = next(i for i, x in enumerate(m["macd"]) if x is not None)
    first_sig = next(i for i, x in enumerate(m["signal"]) if x is not None)
    assert first_line == 25 and first_sig == 25 + 8
    i = len(c) - 1
    assert m["histogram"][i] == approx(m["macd"][i] - m["signal"][i])


def test_stochastic_bounds_and_flat():
    _, _, h, l, c, _ = candles(80)
    s = ind.stochastic(h, l, c)
    assert all(0 <= x <= 100 for x in s["k"] if x is not None)
    assert ind.stochastic([1] * 20, [1] * 20, [1] * 20)["k"][-1] == 50.0


def test_cci_mfi_flat_series():
    assert ind.cci([2] * 25, [1] * 25, [1.5] * 25)[-1] == 0.0
    assert ind.mfi([2] * 20, [1] * 20, [1.5] * 20, [10] * 20)[-1] == 50.0


def test_adx_warmup_and_range():
    _, _, h, l, c, _ = candles(100)
    d = ind.adx(h, l, c, 14)
    assert d["adx"][26] is None and d["adx"][27] is not None
    assert all(0 <= x <= 100 for x in d["adx"] if x is not None)


def test_adx_strong_uptrend_has_plus_di_dominant():
    n = 60
    h = [100 + i * 1.0 + 0.5 for i in range(n)]
    l = [100 + i * 1.0 - 0.5 for i in range(n)]
    c = [100 + i * 1.0 + 0.3 for i in range(n)]
    d = ind.adx(h, l, c)
    assert d["plus_di"][-1] > d["minus_di"][-1] and d["adx"][-1] > 50


def test_supertrend_follows_trend():
    n = 60
    up = ind.supertrend([i + 1.0 for i in range(n)], [i - 1.0 for i in range(n)], [float(i) for i in range(n)])
    assert up["direction"][-1] == 1 and up["supertrend"][-1] < n - 1
    down = ind.supertrend([100 - i + 1.0 for i in range(n)], [100 - i - 1.0 for i in range(n)], [100.0 - i for i in range(n)])
    assert down["direction"][-1] == -1


def test_ichimoku_alignment_no_lookahead():
    _, _, h, l, c, _ = candles(120)
    ic = ind.ichimoku(h, l, c)
    raw_a_at_50 = (ic["tenkan"][50] + ic["kijun"][50]) / 2
    assert ic["span_a"][76] == approx(raw_a_at_50)
    assert ic["chikou"][10] == c[36] and ic["chikou"][-1] is None


def test_parabolic_sar_flips_below_then_above():
    up = [10 + i for i in range(10)] + [19 - i * 2 for i in range(10)]
    hi = [x + 0.5 for x in up]; lo = [x - 0.5 for x in up]
    s = ind.parabolic_sar(hi, lo)
    assert s[5] < lo[5]          # rising: SAR below price
    assert s[-1] > hi[-1]        # falling: SAR above price


def test_obv():
    assert ind.obv([1, 2, 2, 1], [10, 20, 30, 40]) == [0, 20, 20, -20]


def test_vwap_resets_each_utc_day():
    day = 86_400_000
    t = [day * 10 + 0, day * 10 + H, day * 11]       # third bar is next UTC day
    v = ind.vwap(t, [11, 21, 31], [9, 19, 29], [10, 20, 30], [1, 1, 5])
    assert v == [10, 15, 30]


def test_volume_profile_poc_and_value_area():
    h = [10.0] * 9 + [20.0]; l = [9.0] * 9 + [19.0]; c = [9.5] * 9 + [19.5]; v = [10] * 9 + [1]
    vp = ind.volume_profile(h, l, c, v, bins=10)
    assert 9 <= vp["poc"] <= 10.2
    assert sum(b["volume"] for b in vp["bins"]) == 91
    assert vp["value_area_low"] <= vp["poc"] <= vp["value_area_high"]


def test_fibonacci_direction_and_levels():
    f = ind.fibonacci([1, 2, 3, 10, 9], [0, 1, 2, 9, 8])
    assert f["direction"] == "up" and f["levels"]["0"] == 10 and f["levels"]["1"] == 0
    assert f["levels"]["0.5"] == 5


def test_pivots_previous_day_and_daily():
    day = 86_400_000
    t = [day * 10 + i * H for i in range(24)] + [day * 11]
    h = [float(10 + i) for i in range(24)] + [50.0]; l = [float(5 + i) for i in range(24)] + [40.0]; c = [float(8 + i) for i in range(24)] + [45.0]
    p = ind.pivots(t, h, l, c, H)
    H_, L_, C_ = 33.0, 5.0, 31.0
    P = (H_ + L_ + C_) / 3
    assert p["basis"] == "previous UTC day" and p["p"] == approx(P) and p["r1"] == approx(2 * P - L_) and p["s3"] == approx(L_ - 2 * (H_ - P))
    d = ind.pivots([0, day], [10, 12], [8, 9], [9, 11], day)
    assert d["basis"] == "previous bar" and d["p"] == approx(9)


def test_short_inputs_do_not_crash():
    for n in (0, 1, 2, 5):
        t, o, h, l, c, v = candles(n) if n else ([], [], [], [], [], [])
        ind.rsi(c); ind.macd(c); ind.adx(h, l, c); ind.supertrend(h, l, c); ind.ichimoku(h, l, c)
        ind.parabolic_sar(h, l); ind.volume_profile(h, l, c, v); ind.fibonacci(h, l); ind.pivots(t, h, l, c, H)
        ind.stochastic(h, l, c); ind.cci(h, l, c); ind.mfi(h, l, c, v); ind.bollinger(c); ind.keltner(h, l, c)


def test_no_lookahead_values_unchanged_by_future_bars():
    t, o, h, l, c, v = candles(200)
    cut = 150
    full = [ind.rsi(c), ind.macd(c)["macd"], ind.atr(h, l, c), ind.adx(h, l, c)["adx"], ind.supertrend(h, l, c)["supertrend"], ind.parabolic_sar(h, l)]
    part = [ind.rsi(c[:cut]), ind.macd(c[:cut])["macd"], ind.atr(h[:cut], l[:cut], c[:cut]), ind.adx(h[:cut], l[:cut], c[:cut])["adx"],
            ind.supertrend(h[:cut], l[:cut], c[:cut])["supertrend"], ind.parabolic_sar(h[:cut], l[:cut])]
    for f, p in zip(full, part):
        assert f[:cut] == p
