"""The browser (JavaScript) and backend (Python) analysis libraries must produce identical results."""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis import indicators as ind
from app.analysis.patterns import detect_candlestick_patterns, double_tops_bottoms, swing_points
from app.analysis.smc import analyze_smc
from tests.fixtures import H, candles

NODE = shutil.which("node")
RUNNER = Path(__file__).with_name("js_runner.js")


def python_results(t, o, h, l, c, v):
    return {
        "sma": ind.sma(c, 20), "ema": ind.ema(c, 20), "wma": ind.wma(c, 20), "vwma": ind.vwma(c, v, 20), "rsi": ind.rsi(c),
        "macd": ind.macd(c), "stochastic": ind.stochastic(h, l, c), "cci": ind.cci(h, l, c), "mfi": ind.mfi(h, l, c, v),
        "atr": ind.atr(h, l, c), "bollinger": ind.bollinger(c), "keltner": ind.keltner(h, l, c), "adx": ind.adx(h, l, c),
        "supertrend": ind.supertrend(h, l, c), "ichimoku": ind.ichimoku(h, l, c), "psar": ind.parabolic_sar(h, l),
        "obv": ind.obv(c, v), "vwap": ind.vwap(t, h, l, c, v), "volume_profile": ind.volume_profile(h, l, c, v),
        "fibonacci": ind.fibonacci(h, l), "pivots": ind.pivots(t, h, l, c, H),
        "patterns": detect_candlestick_patterns(o, h, l, c), "swings": swing_points(h, l), "formations": double_tops_bottoms(h, l, c),
        "smc": analyze_smc(o, h, l, c),
    }


def same(a, b, path="root"):
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), f"{path}: keys {set(a) ^ set(b)}"
        for k in a:
            same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        assert isinstance(b, list) and len(a) == len(b), f"{path}: length {len(a)} != {len(b) if isinstance(b, list) else b}"
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9), f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("seed", [1, 7, 42])
def test_js_matches_python(seed):
    t, o, h, l, c, v = candles(300, seed=seed)
    payload = json.dumps({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "interval_ms": H})
    js = json.loads(subprocess.run([NODE, str(RUNNER)], input=payload, capture_output=True, text=True, check=True).stdout)
    py = json.loads(json.dumps(python_results(t, o, h, l, c, v)))   # normalise tuples etc.
    assert py["patterns"], "fixture should trigger some patterns"
    smc = py["smc"]
    assert smc["structure"] and smc["order_blocks"] and smc["fvgs"] and smc["liquidity"]["sweeps"], "fixture should exercise SMC"
    same(py, js)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_matches_python_on_every_pattern_scenario():
    from tests.test_patterns import scenario_series
    for name, rows in scenario_series().items():
        o, h, l, c = ([r[k] for r in rows] for k in range(4))
        t = [i * H for i in range(len(rows))]
        v = [100.0] * len(rows)
        payload = json.dumps({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "interval_ms": H})
        js = json.loads(subprocess.run([NODE, str(RUNNER)], input=payload, capture_output=True, text=True, check=True).stdout)
        py = json.loads(json.dumps(detect_candlestick_patterns(o, h, l, c)))
        same(py, js["patterns"], name)
        assert name in {p["pattern"] for p in js["patterns"]}, name
