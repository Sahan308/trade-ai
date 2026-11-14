"""v1.1 research harness — follows research/PROTOCOL.md exactly.

    python research/run_v11.py design  <data_dir>   # design period only; writes research/design_results.json
    python research/run_v11.py holdout <data_dir>   # ONCE: chosen candidate + v1.0.0 on the holdout year

The design run never loads candles at or after HOLDOUT_START. The holdout run refuses to pick a candidate itself:
it reads the choice from design_results.json.
"""
import bisect
import gzip
import json
import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.backtest.core import Backtest, metrics, walk_forward  # noqa: E402
from app.providers.base import INTERVAL_MS  # noqa: E402
from app.signals.engine import evaluate  # noqa: E402
from app.signals.strategy import SMC_TREND_PULLBACK_V1 as V1  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT"]
DESIGN_START = datetime(2023, 11, 15, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2025, 11, 15, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
H, H4 = INTERVAL_MS["1H"], INTERVAL_MS["4H"]

CANDIDATES = {
    "v1.0.0": dict(),
    "A": dict(stop_min_atr=1.0),
    "B": dict(stop_min_atr=1.5),
    "C": dict(stop_min_atr=1.0, htf_required=True),
    "D": dict(stop_min_atr=1.5, htf_required=True),
    "E": dict(stop_min_atr=1.0, htf_required=True, target_mode="r_multiple"),
    "F": dict(stop_min_atr=1.5, htf_required=True, target_mode="r_multiple"),
    "G": dict(stop_min_atr=1.0, htf_required=True, min_risk_cost_ratio=10.0),
}
OUT = os.path.join(os.path.dirname(__file__), "design_results.json")
WINDOW = 300


def cfg_for(cid):
    return replace(V1, version="1.0.0" if cid == "v1.0.0" else f"1.1.0-research-{cid}", **CANDIDATES[cid])


def load(data_dir, sym, tf, start, end):
    d = json.load(gzip.open(os.path.join(data_dir, f"{sym}_{tf}.json.gz"), "rt"))
    a, b = start.timestamp() * 1000, end.timestamp() * 1000
    idx = [i for i, t in enumerate(d["t"]) if a <= t and t + INTERVAL_MS[tf] <= b]   # whole candles inside the period
    return {k: [d[k][i] for i in idx] for k in ("t", "o", "h", "l", "c", "v")}


def candidates_all(series, htf, cids):
    """Per bar: evaluate every candidate on the same closed data, sharing the variant-independent work."""
    loose = {cid: replace(cfg_for(cid), min_score=0, min_rr=-1e9) for cid in cids}
    out = {cid: {} for cid in cids}
    n = len(series["t"])
    for i in range(V1.min_bars - 1, n):
        a = max(0, i + 1 - WINDOW)
        win = {k: series[k][a:i + 1] for k in series}
        now_ms = series["t"][i] + H + 1000
        j = bisect.bisect_right(htf["t"], now_ms - H4)          # 4H candles closed by now
        hw = {k: htf[k][max(0, j - 120):j] for k in htf}
        now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
        memo = {}
        for cid in cids:
            r = evaluate(win, hw, symbol="X", market="spot", source="Binance Spot", cfg=loose[cid], now=now, cache=memo)
            if r["side"] in ("LONG", "SHORT"):
                r["bar_index"] = i
                out[cid][i] = r
    return out


def run_symbol(args):
    data_dir, sym, start, end = args
    t0 = time.time()
    s = load(data_dir, sym, "1H", start, end)
    htf = load(data_dir, sym, "4H", datetime(2023, 1, 1, tzinfo=timezone.utc), end)
    cands = candidates_all(s, htf, list(CANDIDATES))
    res = {}
    for cid, cd in cands.items():
        cfg = cfg_for(cid)
        bt = Backtest(s, None, cfg, symbol=sym, market="spot", source="Binance Spot")
        bt._cands = cd
        full = bt.simulate(cfg.min_score, cfg.min_rr)
        usable = bt.n - (cfg.min_bars - 1)
        wf = walk_forward(bt, cfg, max(100, usable // 3), max(50, usable // 6))
        oos = []
        for f in wf["folds"]:
            a = next(i for i, t in enumerate(s["t"]) if datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat() >= f["test_from"])
            b = next((i for i, t in enumerate(s["t"]) if datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat() >= f["test_to"]), bt.n)
            oos += bt.simulate(f["chosen_min_score"], f["chosen_min_rr"], a, b)["trades"]
        for t in full["trades"] + oos:
            t["symbol"] = sym
        res[cid] = {"trades": full["trades"], "wf_trades": oos, "open_at_end": full["open_at_end"], "folds": wf["folds"]}
    print(f"{sym}: {len(s['t'])} bars in {time.time() - t0:.0f}s", flush=True)
    return sym, res


def pooled(per_symbol, cid, key):
    ts = sorted((t for sym in per_symbol for t in per_symbol[sym][cid][key]), key=lambda t: t["exit_time"])
    return ts


def summary(m):
    return {k: m[k] for k in ("trades", "win_rate", "profit_factor", "expectancy_r", "total_r", "net_pnl_pct", "max_drawdown_pct",
                              "avg_win_r", "avg_loss_r", "warnings")}


def design(data_dir):
    with Pool(2) as p:
        per = dict(p.map(run_symbol, [(data_dir, s, DESIGN_START, HOLDOUT_START) for s in SYMBOLS]))
    table = {}
    for cid in CANDIDATES:
        dm, wm = metrics(pooled(per, cid, "trades")), metrics(pooled(per, cid, "wf_trades"))
        per_sym = {s: round(sum(t["net_r"] for t in per[s][cid]["trades"]), 3) for s in SYMBOLS}
        eligible = cid != "v1.0.0" and dm["trades"] >= 100 and (dm["profit_factor"] or 0) >= 1.0 and (wm["expectancy_r"] or -1) > 0
        table[cid] = {"settings": CANDIDATES[cid], "design": summary(dm), "walk_forward": summary(wm), "per_symbol_total_r": per_sym,
                      "eligible": eligible}
    elig = [c for c in table if table[c]["eligible"]]
    chosen = max(elig, key=lambda c: table[c]["walk_forward"]["expectancy_r"]) if elig else None
    out = {"protocol": "research/PROTOCOL.md", "design_period": [DESIGN_START.isoformat(), HOLDOUT_START.isoformat()],
           "candidates": table, "chosen": chosen,
           "decision": f"Candidate {chosen} selected by highest walk-forward expectancy among eligible candidates."
           if chosen else "No candidate met the eligibility rules. Per protocol, no v1.1 is released."}
    json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps({c: {"design": (v["design"]["trades"], v["design"]["expectancy_r"], v["design"]["profit_factor"]),
                          "wf": (v["walk_forward"]["trades"], v["walk_forward"]["expectancy_r"]), "eligible": v["eligible"]}
                      for c, v in table.items()}, indent=1))
    print("CHOSEN:", chosen)


def holdout(data_dir):
    d = json.load(open(OUT))
    chosen = d["chosen"]
    ids = ["v1.0.0"] + ([chosen] if chosen else [])
    global CANDIDATES
    CANDIDATES = {k: CANDIDATES[k] for k in ids}
    with Pool(2) as p:
        per = dict(p.map(run_symbol, [(data_dir, s, HOLDOUT_START, HOLDOUT_END) for s in SYMBOLS]))
    res = {}
    for cid in ids:
        trades = pooled(per, cid, "trades")
        m = metrics(trades)
        pos = {s: sum(t["net_r"] for t in per[s][cid]["trades"]) for s in SYMBOLS}
        total_pos = sum(v for v in pos.values() if v > 0)
        concentration = max((v / total_pos for v in pos.values() if v > 0), default=None) if total_pos > 0 else None
        checks = {"trades>=50": m["trades"] >= 50, "expectancy>0": (m["expectancy_r"] or -1) > 0,
                  "profit_factor>=1.1": (m["profit_factor"] or 0) >= 1.1,
                  "no_symbol>50%_of_positive_R": concentration is not None and concentration <= 0.5}
        res[cid] = {"metrics": summary(m), "per_symbol_total_r": {k: round(v, 3) for k, v in pos.items()},
                    "max_symbol_share_of_positive_r": concentration, "checks": checks,
                    "passed": cid != "v1.0.0" and all(checks.values()), "by_side": m["by_side"], "by_exit": m["by_exit"]}
    d["holdout"] = {"period": [HOLDOUT_START.isoformat(), HOLDOUT_END.isoformat()], "results": res,
                    "evaluated_at": datetime.now(timezone.utc).isoformat()}
    json.dump(d, open(OUT, "w"), indent=2)
    print(json.dumps({c: {"metrics": r["metrics"], "checks": r["checks"], "passed": r["passed"]} for c, r in res.items()}, indent=1))


if __name__ == "__main__":
    {"design": design, "holdout": holdout}[sys.argv[1]](sys.argv[2])
