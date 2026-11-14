import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.risk.sizing import round_down, round_to, size_position
from tests.test_parity import same

NODE = shutil.which("node")


def test_hand_computed_long_spot():
    r = size_position(1000, 1, 100, 95, "LONG", "spot", fee_rate=0.001, slippage=0.0005)
    per_unit = 5 + 100 * 0.0015 + 95 * 0.0015          # 5.2925
    assert r["per_unit_loss"] == pytest.approx(per_unit)
    assert r["qty"] == pytest.approx(10 / per_unit)       # no step → unrounded
    assert r["actual_risk"] == pytest.approx(10)
    assert r["liquidation_price"] is None


def test_rounds_down_to_step_and_ticks():
    r = size_position(1000, 1, 100.004, 95.006, "LONG", "spot", specs={"step_size": 0.01, "tick_size": 0.01})
    # per-unit loss = 4.998 + 100.004·0.0015 + 95.006·0.0015 = 5.290515 → 10 / 5.290515 = 1.8902 → 1.89
    assert r["qty"] == 1.89 and r["actual_risk"] <= 10
    assert r["entry_rounded"] == 100.0 and r["stop_rounded"] == 95.01
    assert round_down(0.000019999, 0.00001) == 0.00001 and round_to(1.23456, 0.001) == 1.235


def test_minimums_and_margin_warnings():
    small = size_position(10, 0.5, 67000, 66000, "LONG", "spot", specs={"step_size": 0.00001, "min_qty": 0.00001, "min_notional": 5})
    assert any("minimum" in w for w in small["warnings"])
    big = size_position(100, 10, 100, 99.9, "LONG", "futures", leverage=1, specs={"step_size": 0.001})
    assert any("Margin needed" in w for w in big["warnings"]) and any("1–2%" in w for w in big["warnings"])


def test_futures_liquidation_estimate_and_danger():
    r = size_position(1000, 1, 100, 95, "LONG", "futures", leverage=10, specs={"mmr": 0.004})
    assert r["liquidation_price"] == pytest.approx(100 * (1 - 0.1 + 0.004))
    assert r["liquidation_before_stop"] is False
    d = size_position(1000, 1, 100, 85, "LONG", "futures", leverage=10, specs={"mmr": 0.004})
    assert d["liquidation_before_stop"] is True and any("BEFORE the stop" in w for w in d["warnings"])
    s = size_position(1000, 1, 100, 105, "SHORT", "futures", leverage=5)
    assert s["liquidation_price"] == pytest.approx(100 * (1 + 0.2 - 0.005)) and not s["liquidation_before_stop"]


def test_leverage_does_not_change_risk():
    a = size_position(1000, 1, 100, 95, "LONG", "futures", leverage=1)
    b = size_position(1000, 1, 100, 95, "LONG", "futures", leverage=5)
    assert a["qty"] == b["qty"] and a["actual_risk"] == b["actual_risk"] and b["margin"] == pytest.approx(a["margin"] / 5)


def test_funding_cost_sign():
    long_ = size_position(1000, 1, 100, 95, "LONG", "futures", funding_rate=0.0001, hold_hours=24)
    short = size_position(1000, 1, 100, 105, "SHORT", "futures", funding_rate=0.0001, hold_hours=24)
    assert long_["funding_cost"] > 0 and short["funding_cost"] < 0


@pytest.mark.parametrize("args,msg", [
    ((0, 1, 100, 95, "LONG"), "balance"), ((1000, 0, 100, 95, "LONG"), "Risk per trade"),
    ((1000, 1, 100, 105, "LONG"), "stop must be below"), ((1000, 1, 100, 95, "SHORT"), "above entry"),
])
def test_validation(args, msg):
    r = size_position(*args)
    assert not r["valid"] and any(msg in e for e in r["errors"])


def test_spot_rejects_leverage():
    assert not size_position(1000, 1, 100, 95, "LONG", "spot", leverage=3)["valid"]


CASES = [
    dict(balance=1000, riskPct=1, entry=100, stop=95, side="LONG", market="spot"),
    dict(balance=2500, riskPct=0.75, entry=67250.5, stop=66410.2, side="LONG", market="spot", specs={"tick_size": 0.01, "step_size": 0.00001, "min_qty": 0.00001, "min_notional": 5}),
    dict(balance=500, riskPct=2, entry=75.73, stop=77.12, side="SHORT", market="futures", leverage=10, feeRate=0.0005, specs={"tick_size": 0.01, "step_size": 0.01, "min_qty": 0.01, "min_notional": 5, "mmr": 0.025}, fundingRate=-0.00006, holdHours=16),
    dict(balance=100, riskPct=5, entry=0.989, stop=0.95, side="LONG", market="futures", leverage=50, specs={"step_size": 0.1, "tick_size": 0.0001}),
    dict(balance=1000, riskPct=1, entry=100, stop=105, side="LONG"),
]


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("case", CASES)
def test_js_sizing_matches_python(case):
    js_src = Path(__file__).resolve().parents[2] / "assets/js/analysis/risk.js"
    code = f"globalThis.window=globalThis; require({json.dumps(str(js_src))}); process.stdout.write(JSON.stringify(TA.Risk.sizePosition({json.dumps(case)})))"
    js = json.loads(subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout)
    kw = dict(balance=case["balance"], risk_pct=case["riskPct"], entry=case["entry"], stop=case["stop"], side=case["side"],
              market=case.get("market", "spot"), leverage=case.get("leverage", 1), fee_rate=case.get("feeRate", 0.001),
              specs=case.get("specs"), funding_rate=case.get("fundingRate"), hold_hours=case.get("holdHours", 0))
    same(json.loads(json.dumps(size_position(**kw))), js)
