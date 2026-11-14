"""Backtest correctness: no look-ahead, no overlapping trades, metrics maths, splits and walk-forward."""
from datetime import datetime

import pytest

from app.backtest.core import GRID, Backtest, chronological_splits, metrics, run, walk_forward
from app.signals.lifecycle import track
from app.signals.strategy import SMC_TREND_PULLBACK_V1 as CFG
from tests.fixtures import candles
from tests.test_lifecycle import at_end, bars, sig


def series(n=900, seed=9):
    t, o, h, l, c, v = candles(n, seed=seed)
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


@pytest.fixture(scope="module")
def result():
    return run(series(), None, CFG, symbol="TESTUSDT", market="futures", source="fixture", funding_rate_8h=0.0001)


def test_decisions_do_not_change_when_future_data_is_added():
    short = Backtest(series(700), None, CFG, symbol="T", market="spot", source="f").candidates()
    long_ = Backtest(series(900), None, CFG, symbol="T", market="spot", source="f").candidates()
    common = {i: c for i, c in long_.items() if i < 700}
    assert set(short) == set(common)
    for i in short:
        a, b = dict(short[i]), dict(common[i])
        assert (a["side"], a["entry_low"], a["stop"], a["targets"], a["score"]) == (b["side"], b["entry_low"], b["stop"], b["targets"], b["score"])


def test_trades_never_overlap_and_fill_after_the_decision(result):
    trades = result["trades"]
    assert trades, "fixture should produce trades"
    for t in trades:
        assert t["entry_time"] >= t["signal_time"]
    for a, b in zip(trades, trades[1:]):
        assert b["entry_time"] >= a["exit_time"] or b["signal_time"] >= a["exit_time"]


def test_latency_delays_fills():
    s = series()
    bt0 = Backtest(s, None, CFG, symbol="T", market="spot", source="f")
    bt2 = Backtest(s, None, CFG, symbol="T", market="spot", source="f", latency_bars=2)
    i = next(iter(bt0.candidates()))
    bt2.candidates()
    t0, t2 = bt0.outcome(i)["trade"], bt2.outcome(i)["trade"]
    if t0 and t2:
        assert t2["entry_time"] >= t0["entry_time"]


def test_funding_charged_to_longs_when_positive():
    s = series()
    free = Backtest(s, None, CFG, symbol="T", market="futures", source="f")
    paid = Backtest(s, None, CFG, symbol="T", market="futures", source="f", funding_rate_8h=0.001)
    for i, c in free.candidates().items():
        paid.candidates()
        a, b = free.outcome(i)["trade"], paid.outcome(i)["trade"]
        if a and a["hours"] > 0:
            assert (b["net_r"] < a["net_r"]) if c["side"] == "LONG" else (b["net_r"] > a["net_r"])
            return
    pytest.skip("no filled trade with holding time in fixture")


def test_metrics_hand_computed():
    ts = [{"net_r": r, "exit_time": f"2026-0{m}-01T00:00:00+00:00", "side": s, "exit": "stop", "regime": "x"}
          for r, m, s in [(2.0, 1, "LONG"), (-1.0, 1, "SHORT"), (-1.0, 2, "LONG"), (0.5, 2, "LONG")]]
    m = metrics(ts, risk_pct=1.0)
    assert m["trades"] == 4 and m["wins"] == 2 and m["losses"] == 2 and m["win_rate"] == 0.5
    assert m["profit_factor"] == pytest.approx(2.5 / 2) and m["expectancy_r"] == pytest.approx(0.125)
    assert m["avg_win_r"] == pytest.approx(1.25) and m["avg_loss_r"] == pytest.approx(-1.0)
    eq = 1.02 * 0.99 * 0.99 * 1.005
    assert m["net_pnl_pct"] == pytest.approx((eq - 1) * 100, abs=1e-3)
    assert m["max_drawdown_pct"] == pytest.approx((1 - 0.99 * 0.99) * 100, abs=1e-3)
    assert m["max_consecutive_losses"] == 2
    assert m["by_side"]["LONG"]["trades"] == 3 and m["by_month"]["2026-01"]["total_r"] == 1.0
    assert m["warnings"] and "too few" in m["warnings"][0]
    assert metrics([])["win_rate"] is None and metrics([])["profit_factor"] is None


def test_splits_are_chronological_and_disjoint(result):
    sp = result["splits"]
    assert sp["development"]["to"] <= sp["validation"]["from"] and sp["validation"]["to"] <= sp["out_of_sample"]["from"]
    assert "Untouched" in sp["out_of_sample"]["note"]


def test_walk_forward_tests_only_unseen_windows(result):
    wf = result["walk_forward"]
    assert wf["folds"]
    for f in wf["folds"]:
        assert f["train_to"] <= f["test_from"]
        assert (f["chosen_min_score"], f["chosen_min_rr"]) in GRID + [(CFG.min_score, CFG.min_rr)]
    for a, b in zip(wf["folds"], wf["folds"][1:]):
        assert a["test_to"] <= b["test_from"]


def test_result_is_labelled_backtest(result):
    assert result["kind"] == "backtest" and "not a measure of live accuracy" in result["disclaimer"]
    assert result["assumptions"]["same_candle_rule"] == "stop first"


def test_resolver_target_first_credits_target_then_stop():
    b = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 97.5, 101)])
    r = track(sig(), b, at_end(b), resolver=lambda *a: "target_first")
    assert [e["type"] for e in r["events"]] == ["triggered", "tp1_hit", "stopped"]
    assert r["events"][-1]["detail"]["ambiguous_same_candle"] is False
    assert r["outcome"]["gross_r"] == pytest.approx((1 - 2) / 3, abs=1e-6)
    s = track(sig(), b, at_end(b), resolver=lambda *a: None)
    assert [e["type"] for e in s["events"]] == ["triggered", "stopped"] and s["events"][-1]["detail"]["ambiguous_same_candle"]
