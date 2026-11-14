"""Lifecycle rules on hand-built candles (1H). Signal: LONG, entry 99–100, stop 98, targets 102/104/106."""
from datetime import datetime, timezone

import pytest

from app.signals.lifecycle import track

H = 3_600_000
T0 = 1_794_643_200_000


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def sig(side="LONG", expiry_bars=12, **over):
    base = {"side": side, "timeframe": "1H", "data_as_of": iso(T0), "expires_at": iso(T0 + expiry_bars * H),
            "entry_low": 99.0, "entry_high": 100.0, "stop": 98.0, "targets": [102.0, 104.0, 106.0],
            "config": {"expiry_bars": expiry_bars}, "assumptions": {"fee_rate_per_side": 0.0, "slippage_per_side": 0.0}}
    if side == "SHORT":
        base.update(entry_low=100.0, entry_high=101.0, stop=102.0, targets=[98.0, 96.0, 94.0])
    base.update(over)
    return base


def bars(rows, start=T0):
    """rows: (o, h, l, c) for consecutive candles opening at start, start+H, …"""
    return {"t": [start + i * H for i in range(len(rows))], "o": [r[0] for r in rows], "h": [r[1] for r in rows],
            "l": [r[2] for r in rows], "c": [r[3] for r in rows], "v": [1.0] * len(rows)}


def at_end(s, extra=1):
    return datetime.fromtimestamp((s["t"][-1] + H * extra) / 1000, tz=timezone.utc)


def types(r):
    return [e["type"] for e in r["events"]]


def test_waiting_for_entry():
    s = bars([(101, 101.5, 100.5, 101)] * 3)
    r = track(sig(), s, at_end(s))
    assert r["lifecycle"] == "active" and not r["events"] and not r["terminal"]


def test_trigger_then_all_targets():
    s = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 100.2, 102.2), (102.2, 104.2, 102, 104), (104, 106.5, 103.8, 106)])
    r = track(sig(), s, at_end(s))
    assert types(r) == ["triggered", "tp1_hit", "tp2_hit", "tp3_hit"]
    assert r["events"][0]["price"] == 100.0                      # filled at the worse zone edge
    assert r["lifecycle"] == "target_reached" and r["terminal"]
    assert r["outcome"]["gross_r"] == pytest.approx((2 + 4 + 6) / 2 / 3)   # thirds at +1R, +2R, +3R


def test_stop_after_tp1_is_stopped_with_partial():
    s = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 100.2, 102.2), (102, 102.1, 97.5, 97.8)])
    r = track(sig(), s, at_end(s))
    assert types(r) == ["triggered", "tp1_hit", "stopped"] and r["lifecycle"] == "stopped"
    assert r["outcome"]["gross_r"] == pytest.approx((1 + (-1) * 2) / 3, abs=1e-6)


def test_same_candle_stop_and_target_assumes_stop():
    s = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 97.5, 101)])
    r = track(sig(), s, at_end(s))
    assert types(r) == ["triggered", "stopped"]
    assert r["events"][-1]["detail"]["ambiguous_same_candle"] is True
    assert r["outcome"]["gross_r"] == pytest.approx(-1, abs=1e-6)


def test_stop_on_entry_candle():
    s = bars([(101, 101.2, 97.0, 97.5)])
    r = track(sig(), s, at_end(s))
    assert types(r) == ["triggered", "stopped"] and r["events"][1]["detail"]["ambiguous_same_candle"]


def test_targets_not_credited_on_entry_candle():
    s = bars([(101, 103, 99.8, 102.5)])
    r = track(sig(), s, at_end(s))
    assert types(r) == ["triggered"] and r["lifecycle"] == "triggered"


def test_gap_open_inside_zone_fills_at_open():
    s = bars([(99.5, 100.2, 99.3, 99.9)])
    assert track(sig(), s, at_end(s))["events"][0]["price"] == 99.5


def test_invalidated_before_entry():
    # never touches the zone from above? A close below the stop without touching is impossible for a long
    # (it would trade through the zone), so use a short: price closes above the stop without reaching entry_low… mirror:
    s = bars([(99, 99.5, 98.5, 99.2), (99.2, 99.6, 98.8, 99.4)])
    r = track(sig("SHORT", stop=99.3, entry_low=100.0, entry_high=101.0, targets=[98, 96, 94]), s, at_end(s))
    assert types(r) == ["invalidated"] and r["lifecycle"] == "invalidated" and r["outcome"] is None


def test_expired_without_entry():
    s = bars([(101, 101.5, 100.5, 101)] * 5)
    r = track(sig(expiry_bars=3), s, at_end(s))
    assert types(r) == ["expired"] and r["lifecycle"] == "expired" and r["outcome"] is None


def test_time_exit_after_max_hold():
    rows = [(101, 101.2, 99.8, 100.5)] + [(100.5, 101, 99.5, 100.8)] * 6
    s = bars(rows)
    r = track(sig(), s, at_end(s), max_hold_bars=4)
    assert types(r)[-1] == "expired" and r["outcome"]["exit"] == "time"
    assert r["outcome"]["gross_r"] == pytest.approx((100.8 - 100) / 2, abs=1e-6)


def test_short_mirror():
    s = bars([(99.5, 100.2, 99.4, 99.9), (99.9, 100, 97.8, 98.1), (98, 101.5, 97.9, 101)])
    r = track(sig("SHORT"), s, at_end(s))
    assert types(r) == ["triggered", "tp1_hit"]
    assert r["events"][0]["price"] == 100.0 and r["lifecycle"] == "target_reached" and not r["terminal"]


def test_forming_candle_and_pre_signal_candles_ignored():
    early = bars([(99, 99.5, 97, 97.5)], start=T0 - H)          # before the signal's data_as_of
    s = {k: early[k] + bars([(101, 101.2, 100.6, 101)])[k] for k in early}
    r = track(sig(), s, datetime.fromtimestamp((T0 + H / 2) / 1000, tz=timezone.utc))   # last candle still forming
    assert r["events"] == [] and r["lifecycle"] == "active"


def test_costs_reduce_net_r():
    s = bars([(101, 101.2, 99.8, 100.5), (100.5, 102.5, 97.5, 101)])
    r = track(sig(assumptions={"fee_rate_per_side": 0.001, "slippage_per_side": 0.0005}), s, at_end(s))
    assert r["outcome"]["net_r"] < r["outcome"]["gross_r"]


def test_no_trade_is_untouched():
    assert track({"side": "NO TRADE", "lifecycle": "no_trade"}, bars([]), at_end(bars([(1, 1, 1, 1)])))["events"] == []
