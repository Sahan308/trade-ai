"""SMC rules on hand-built price paths."""
from app.analysis.smc import analyze_smc, fair_value_gaps, liquidity, order_blocks, premium_discount, structure
from tests.fixtures import candles


def path_to_ohlc(closes, wick=0.2):
    """Each bar: small body in the direction of the move, high/low = close ± (body + wick).
    Highs and lows therefore depend only on that bar's close, so peaks are strict."""
    o, h, l = [], [], []
    for i, c in enumerate(closes):
        up = i == 0 or c >= closes[i - 1]
        op = c - 0.1 if up else c + 0.1
        o.append(op); h.append(max(op, c) + wick); l.append(min(op, c) - wick)
    return o, h, l, list(closes)


# up-leg to a peak at bar 6, pullback to a trough at bar 12, rally through the peak (bullish BOS),
# then a sell-off through the trough (bearish CHOCH).
UP_DOWN = [10, 11, 12, 13, 14, 15, 16, 15, 14, 13, 12, 11.5, 11, 12, 13, 14, 15, 16, 17, 18, 17.5, 17, 16, 15, 14, 13, 12, 11, 10.5, 10]


def test_bos_then_choch():
    o, h, l, c = path_to_ohlc(UP_DOWN)
    ev = structure(o, h, l, c)
    kinds = [(e["type"], e["direction"]) for e in ev]
    assert kinds[0] == ("BOS", "bullish")
    assert ("CHOCH", "bearish") in kinds
    first = ev[0]
    assert first["swing_index"] == 6 and first["level"] == h[6] and c[first["index"]] > h[6]
    assert all(e["index"] >= e["swing_index"] + 3 for e in ev)   # only confirmed swings are broken


def test_order_block_is_last_opposite_candle_and_gets_status():
    o, h, l, c = path_to_ohlc(UP_DOWN)
    ev = structure(o, h, l, c)
    obs = order_blocks(o, h, l, c, ev)
    bull = next(x for x in obs if x["direction"] == "bullish")
    assert c[bull["index"]] < o[bull["index"]]                        # bearish candle
    assert bull["index"] < ev[0]["index"]
    assert all(not (c[i] < o[i]) for i in range(bull["index"] + 1, ev[0]["index"]))  # it is the LAST one
    assert bull["status"] in ("mitigated", "broken")                  # price later fell back through


def test_fvg_detection_and_fill():
    # 15 quiet bars (ATR warm-up), then: bar 15 high 10.5, bar 17 low 12.0 → bullish gap [10.5, 12.0] at bar 16;
    # a few bars later price falls back through the whole gap → filled.
    o = [10.0] * 15 + [10.0, 10.4, 12.3, 12.4, 12.3, 11.0, 10.0]
    c = [10.1] * 15 + [10.4, 12.3, 12.4, 12.3, 11.0, 10.0, 9.5]
    h = [10.3] * 15 + [10.5, 12.4, 12.6, 12.5, 12.4, 11.1, 10.1]
    l = [9.9] * 15 + [9.9, 10.3, 12.0, 12.2, 10.9, 9.9, 9.4]
    gaps = [g for g in fair_value_gaps(h, l, c, min_fvg_atr=0) if g["direction"] == "bullish" and g["index"] == 16]
    assert gaps and gaps[0]["low"] == 10.5 and gaps[0]["high"] == 12.0
    assert gaps[0]["touched_index"] == 19 and gaps[0]["status"] == "filled" and gaps[0]["filled_index"] == 20


def test_fvg_needs_atr_history():
    assert fair_value_gaps([1, 2, 3], [0, 1, 2], [0.5, 1.5, 2.5]) == []


def test_liquidity_sweep_vs_take():
    # swing high at bar 5 (=11.2); bar 12 wicks above and closes back below → sweep
    closes = [10, 10.2, 10.4, 10.6, 10.8, 11.0, 10.8, 10.6, 10.4, 10.3, 10.4, 10.6, 10.9, 10.7, 10.5]
    o, h, l, c = path_to_ohlc(closes)
    h[12] = 11.6
    liq = liquidity(h, l, c)
    bsl = next(x for x in liq["levels"] if x["side"] == "BSL" and x["index"] == 5)
    assert bsl["status"] == "swept" and bsl["event_index"] == 12
    c2 = list(c); c2[12] = 11.5; o2, h2, l2, _ = path_to_ohlc(c2)
    taken = next(x for x in liquidity(h2, l2, c2)["levels"] if x["side"] == "BSL" and x["index"] == 5)
    assert taken["status"] == "taken"


def test_equal_highs_flagged():
    closes = [10, 11, 12, 13, 12, 11, 10, 11, 12, 13.005, 12, 11, 10, 9, 8]
    o, h, l, c = path_to_ohlc(closes)
    eq = [x for x in liquidity(h, l, c)["levels"] if x["side"] == "BSL"]
    assert len(eq) == 2 and all(x["equal"] for x in eq)


def test_premium_discount():
    o, h, l, c = path_to_ohlc(UP_DOWN)
    pd = premium_discount(h, l, c)
    assert pd["range_low"] < pd["equilibrium"] < pd["range_high"]
    assert pd["zone"] == ("premium" if c[-1] > pd["equilibrium"] else "discount")
    assert premium_discount([1, 2], [0, 1], [0.5, 1.5]) is None


def test_no_lookahead_in_structure():
    t, o, h, l, c, v = candles(250, seed=11)
    full = structure(o, h, l, c)
    cut = 180
    part = structure(o[:cut], h[:cut], l[:cut], c[:cut])
    assert [e for e in full if e["index"] < cut] == part


def test_analyze_smc_on_fixture():
    t, o, h, l, c, v = candles(300, seed=7)
    s = analyze_smc(o, h, l, c)
    assert s["structure"] and s["trend"] in ("bullish", "bearish")
    assert {"order_blocks", "fvgs", "liquidity", "premium_discount", "inducements"} <= set(s)
