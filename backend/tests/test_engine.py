"""Signal engine behaviour: valid outputs, every NO TRADE path, determinism and no look-ahead."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.signals.engine import evaluate
from app.signals.strategy import SMC_TREND_PULLBACK_V1 as CFG
from tests.fixtures import H, candles


def series(seed, n=300, mirror=False):
    t, o, h, l, c, v = candles(n, seed=seed)
    if mirror:   # flip the chart upside down: downtrends become uptrends
        K = 2 * max(h) + 10
        o, h, l, c = [K - x for x in o], [K - x for x in l], [K - x for x in h], [K - x for x in c]
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def now_after(s, seconds=5):
    return datetime.fromtimestamp((s["t"][-1] + H) / 1000 + seconds, tz=timezone.utc)


def run(s, **kw):
    kw.setdefault("now", now_after(s))
    return evaluate(s, None, symbol="TESTUSDT", market=kw.pop("market", "futures"), source="fixture", cfg=kw.pop("cfg", CFG), **kw)


def all_results():
    out = []
    for seed in range(1, 120):
        for mirror in (False, True):
            out.append(run(series(seed, mirror=mirror)))
    return out


RESULTS = None


def results():
    global RESULTS
    if RESULTS is None:
        RESULTS = all_results()
    return RESULTS


def test_engine_can_emit_both_sides_and_no_trade():
    sides = {r["side"] for r in results()}
    assert {"LONG", "SHORT", "NO TRADE"} <= sides


def test_emitted_signals_are_internally_consistent():
    for r in results():
        if r["side"] == "NO TRADE":
            assert r["reasons"] and r["explanation"].startswith("No trade") and r["lifecycle"] == "no_trade"
            continue
        long_ = r["side"] == "LONG"
        lo, hi, stop, tps = r["entry_low"], r["entry_high"], r["stop"], r["targets"]
        assert len(tps) == 3
        risk = abs((lo + hi) / 2 - stop)
        assert all(abs(b - a) >= 0.5 * risk - 1e-9 for a, b in zip(tps, tps[1:]))
        if long_:
            assert stop < lo <= hi < tps[0] < tps[1] < tps[2]
        else:
            assert stop > hi >= lo > tps[0] > tps[1] > tps[2]
        assert r["rr_net"] >= CFG.min_rr and r["score"] >= CFG.min_score and 0 <= r["score"] <= 100
        assert r["supporting"] and all(x["weight"] > 0 for x in r["supporting"] + r["conflicting"])
        assert r["score"] == max(0, min(100, sum(x["weight"] for x in r["supporting"]) - sum(x["weight"] for x in r["conflicting"])))
        assert "not a win probability" in r["score_note"].lower()
        assert r["invalidation"] and r["entry_logic"] and r["assumptions"]["fee_rate_per_side"] > 0
        assert r["config"]["version"] == "1.0.0" and r["config_hash"] == CFG.hash()
        assert r["fingerprint"].startswith(f"TESTUSDT|futures|1H|{r['side']}|smc_trend_pullback@1.0.0|")


def test_not_enough_history():
    r = run(series(3, n=120))
    assert r["side"] == "NO TRADE" and "not enough history" in r["reasons"][0]


def test_stale_data():
    s = series(3)
    r = run(s, now=now_after(s, seconds=3 * 3600))
    assert r["side"] == "NO TRADE" and "stale" in r["reasons"][0]


def test_gaps():
    r = run(series(3), gaps=5)
    assert r["side"] == "NO TRADE" and "missing candles" in r["reasons"][0]


def test_forming_candle_and_future_candles_are_ignored():
    s = series(65)
    now = now_after(s)
    base = run(s, now=now)
    # append a "future" candle that hasn't closed yet at `now` — result must not change
    s2 = {k: list(v) for k, v in s.items()}
    for k, v in zip("tohlcv", (s["t"][-1] + H, 1.0, 1e9, 0.5, 1e8, 1e9)):
        s2[k].append(v)
    assert run(s2, now=now) == base
    # evaluating mid-way through the last candle ignores that candle
    mid = run(s, now=now - timedelta(minutes=30))
    assert mid["data_as_of"] < base["data_as_of"]


def test_deterministic():
    s = series(65)
    assert run(s) == run(s)


def test_stricter_config_turns_signal_into_no_trade_and_changes_hash():
    emitted = next(r for r in results() if r["side"] != "NO TRADE")
    strict = replace(CFG, min_score=101)
    assert strict.hash() != CFG.hash()
    seed_hit = None
    for seed in range(1, 120):
        for mirror in (False, True):
            s = series(seed, mirror=mirror)
            if run(s)["side"] != "NO TRADE":
                seed_hit = s
                break
        if seed_hit:
            break
    r = run(seed_hit, cfg=strict)
    assert r["side"] == "NO TRADE" and any("below the minimum 101" in x for x in r["reasons"])
    assert r["candidate_side"] == emitted["side"] or r["candidate_side"] in ("LONG", "SHORT")


def test_futures_funding_is_used_as_evidence():
    for r0 in results():
        if r0["side"] == "LONG":
            break
    else:
        pytest.skip("no LONG in fixtures")
    # find the series again and re-run with extreme positive funding (crowded longs)
    for seed in range(1, 120):
        for mirror in (False, True):
            s = series(seed, mirror=mirror)
            r = run(s)
            if r["side"] == "LONG":
                crowded = run(s, funding_rate=0.002)
                assert any(x["factor"] == "Funding" for x in crowded["conflicting"])
                assert (crowded.get("score") or 0) <= r["score"]
                return
