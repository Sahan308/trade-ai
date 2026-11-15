"""Round-4 research harness: portfolio trend-following. Follows research/PROTOCOL_R4.md exactly.

    python research/run_r4.py design  <data_dir>   # 2020-2021 only -> research/design_results_r4.json
    python research/run_r4.py holdout <data_dir>   # ONCE: chosen candidate on 2022-01-01 .. 2023-11-14
    python research/run_r4.py context <data_dir>   # chosen candidate on 2023-11-15 .. 2026-11-14 (already-seen data)

Pure Python. Each run only loads candles that CLOSE before its period end (design never sees 2022+).
"""
import gzip
import json
import math
import os
import sys
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "TRXUSDT", "XLMUSDT",
           "ETCUSDT", "BCHUSDT", "EOSUSDT", "ATOMUSDT", "XTZUSDT", "NEOUSDT", "VETUSDT", "ZECUSDT", "DASHUSDT", "QTUMUSDT",
           "SOLUSDT", "DOTUSDT", "AVAXUSDT", "UNIUSDT", "FILUSDT"]
D = lambda y, m, d: datetime(y, m, d, tzinfo=timezone.utc)  # noqa: E731
PERIODS = {"design": (D(2020, 1, 1), D(2022, 1, 1)), "holdout": (D(2022, 1, 1), D(2023, 11, 15)),
           "context": (D(2023, 11, 15), D(2026, 11, 14))}
DAY = 86_400_000
COST = 0.0015
LOOKBACKS = [5, 10, 20, 30, 60, 90, 150, 250, 360]
TOP_N, MIN_HIST, VOL_TARGET, BAND = 20, 365, 0.25, 0.20
OUT = os.path.join(os.path.dirname(__file__), "design_results_r4.json")
CANDIDATES = ["E1", "E2", "E3", "E4"]
MS = lambda d: int(d.timestamp() * 1000)  # noqa: E731


def load(data_dir, end_ms):
    data, missing = {}, []
    for s in SYMBOLS:
        p = os.path.join(data_dir, f"{s}_1D.json.gz")
        if not os.path.exists(p):
            missing.append(s); continue
        d = json.load(gzip.open(p, "rt"))
        keep = [i for i, t in enumerate(d["t"]) if t + DAY <= end_ms]
        if keep:
            data[s] = {k: [d[k][i] for i in keep] for k in ("t", "o", "c", "v")}
    return data, missing


def ensemble_scores(c):
    """Per day: fraction of the 9 Donchian sub-signals that are ON (close-based, trailing midpoint stop)."""
    n = len(c)
    score = [0.0] * n
    for L in LOOKBACKS:
        on, stop = False, None
        for i in range(n):
            if i < L:
                continue
            w = c[i - L:i]
            hi, lo = max(w), min(w)
            if not on and c[i] > hi:
                on, stop = True, (hi + lo) / 2
            elif on:
                stop = max(stop, (hi + lo) / 2)
                if c[i] < stop:
                    on, stop = False, None
            if on:
                score[i] += 1 / len(LOOKBACKS)
    return score


def ann_vol(c, i, n=90):
    if i < n:
        return None
    r = [math.log(c[k] / c[k - 1]) for k in range(i - n + 1, i + 1)]
    m = sum(r) / n
    return (sum((x - m) ** 2 for x in r) / (n - 1)) ** 0.5 * math.sqrt(365)


def simulate(data, cid, start, end):
    days = sorted({t for d in data.values() for t in d["t"] if MS(start) - DAY <= t < MS(end)})
    idx = {s: {t: i for i, t in enumerate(d["t"])} for s, d in data.items()}
    scores = {s: ensemble_scores(d["c"]) for s, d in data.items()} if cid in ("E1", "E2", "E3") else {}
    btc_score = ensemble_scores(data["BTCUSDT"]["c"]) if cid == "E3" else None
    w = {}            # current weights (fraction of equity) per symbol, after last rebalance
    eq, curve, turnover, exposure = 1.0, [], 0.0, []
    for k, t in enumerate(days[:-1]):
        t_next = days[k + 1]
        # 1) signals from day t's close -> targets
        elig = []
        for s, d in data.items():
            i = idx[s].get(t)
            if i is None or i + 1 < MIN_HIST:
                continue
            qv = sorted(d["c"][j] * d["v"][j] for j in range(max(0, i - 29), i + 1))
            elig.append((qv[len(qv) // 2], s, i))
        elig = [x for x in sorted(elig, reverse=True)[:TOP_N]]
        target = {}
        if cid.startswith("B"):
            pass
        for _, s, i in elig:
            c = data[s]["c"]
            if cid in ("E1", "E2", "E3"):
                sc = scores[s][i]
                if sc <= 0:
                    continue
                if cid == "E2":
                    raw = sc
                else:
                    v = ann_vol(c, i)
                    if not v:
                        continue
                    raw = sc * min(1.0, VOL_TARGET / v)
            elif cid == "E4":
                if i < 90 or c[i] / c[i - 90] - 1 <= 0:
                    continue
                v = ann_vol(c, i)
                if not v:
                    continue
                raw = min(1.0, VOL_TARGET / v)
            target[s] = min(raw, 1 / TOP_N) if cid != "E2" else raw
        if cid == "E2":   # equal-score weights, same caps
            target = {s: min(x, 1 / TOP_N) for s, x in target.items()}
        if cid == "E3":
            bi = idx["BTCUSDT"].get(t)
            if bi is not None and btc_score[bi] < 0.5:
                target = {s: x / 2 for s, x in target.items()}
        tot = sum(target.values())
        if tot > 1:
            target = {s: x / tot for s, x in target.items()}
        # 2) rebalance at next open with band; cost on traded notional
        new_w = dict(w)
        for s in set(w) | set(target):
            cur, tgt = w.get(s, 0.0), target.get(s, 0.0)
            if (cur == 0) != (tgt == 0) or (tgt > 0 and abs(tgt - cur) > BAND * tgt):
                turnover += abs(tgt - cur)
                eq -= abs(tgt - cur) * eq * COST
                new_w[s] = tgt
        w = {s: x for s, x in new_w.items() if x > 0}
        # 3) hold from next open to the open after (approx. by open-to-open return), weights drift
        r_port = 0.0
        for s, x in w.items():
            d, i1 = data[s], idx[s].get(t_next)
            i2 = idx[s].get(days[k + 2]) if k + 2 < len(days) else None
            if i1 is None:
                continue
            px1 = d["o"][i1]
            px2 = d["o"][i2] if i2 is not None else d["c"][i1]
            r_port += x * (px2 / px1 - 1)
        eq *= 1 + r_port
        # drift weights
        if r_port > -1:
            for s in list(w):
                d, i1 = data[s], idx[s].get(t_next)
                i2 = idx[s].get(days[k + 2]) if k + 2 < len(days) else None
                if i1 is not None:
                    px2 = d["o"][i2] if i2 is not None else d["c"][i1]
                    w[s] = w[s] * (px2 / d["o"][i1]) / (1 + r_port)
        exposure.append(sum(w.values()))
        curve.append((t_next, eq))
    return curve, turnover, (sum(exposure) / len(exposure) if exposure else 0)


def benchmark(data, kind, start, end):
    days = sorted({t for d in data.values() for t in d["t"] if MS(start) <= t < MS(end)})
    idx = {s: {t: i for i, t in enumerate(d["t"])} for s, d in data.items()}
    eq, curve, w, month = 1.0, [], {}, None
    for k, t in enumerate(days[:-1]):
        t2 = days[k + 1]
        m = datetime.fromtimestamp(t / 1000, timezone.utc).month
        if kind == "btc":
            if not w:
                w = {"BTCUSDT": 1.0}; eq *= 1 - COST
        elif m != month:
            month = m
            elig = []
            for s, d in data.items():
                i = idx[s].get(t)
                if i is None or i + 1 < MIN_HIST:
                    continue
                qv = sorted(d["c"][j] * d["v"][j] for j in range(max(0, i - 29), i + 1))
                elig.append((qv[len(qv) // 2], s))
            elig = [s for _, s in sorted(elig, reverse=True)[:TOP_N]]
            tgt = {s: 1 / len(elig) for s in elig} if elig else {}
            eq *= 1 - COST * sum(abs(tgt.get(s, 0) - w.get(s, 0)) for s in set(tgt) | set(w))
            w = tgt
        r = 0.0
        for s, x in w.items():
            i1, i2 = idx[s].get(t), idx[s].get(t2)
            if i1 is not None and i2 is not None:
                r += x * (data[s]["c"][i2] / data[s]["c"][i1] - 1)
        eq *= 1 + r
        for s in list(w):
            i1, i2 = idx[s].get(t), idx[s].get(t2)
            if i1 is not None and i2 is not None and r > -1:
                w[s] = w[s] * (data[s]["c"][i2] / data[s]["c"][i1]) / (1 + r)
        curve.append((t2, eq))
    return curve


def metrics(curve, start, end, turnover=None, exposure=None):
    pts = [(t, e) for t, e in curve if MS(start) <= t <= MS(end)]
    if len(pts) < 2:
        return None
    e0, e1 = pts[0][1], pts[-1][1]
    years = (pts[-1][0] - pts[0][0]) / DAY / 365
    rets = [pts[i][1] / pts[i - 1][1] - 1 for i in range(1, len(pts))]
    mu = sum(rets) / len(rets)
    sd = (sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
    peak, mdd = -1, 0
    for _, e in pts:
        peak = max(peak, e); mdd = min(mdd, e / peak - 1)
    out = dict(total_return=round(e1 / e0 - 1, 4), cagr=round((e1 / e0) ** (1 / years) - 1, 4) if years > 0 else None,
               sharpe=round(mu / sd * math.sqrt(365), 3) if sd > 0 else None, max_drawdown=round(mdd, 4), days=len(pts))
    if turnover is not None:
        out["turnover_per_year"] = round(turnover / years, 2)
    if exposure is not None:
        out["avg_exposure"] = round(exposure, 3)
    return out


def main(mode, data_dir):
    start, end = PERIODS[mode]
    data, missing = load(data_dir, MS(end))
    if mode == "design":
        cids = CANDIDATES
    else:
        chosen = json.load(open(OUT)).get("chosen")
        if not chosen:
            sys.exit("No eligible candidate in design: holdout stays unused (protocol).")
        cids = [chosen]
    res = {}
    for cid in cids:
        curve, to, ex = simulate(data, cid, start, end)
        res[cid] = metrics(curve, start, end, to, ex)
    bench = {"btc_buy_hold": metrics(benchmark(data, "btc", start, end), start, end),
             "equal_weight_top20": metrics(benchmark(data, "ew", start, end), start, end)}
    if mode == "design":
        for cid, m in res.items():
            m["eligible"] = bool(m["cagr"] > 0 and m["sharpe"] and m["sharpe"] >= 1.0 and m["max_drawdown"] >= -0.40 and m["avg_exposure"] >= 0.10)
        elig = [c for c in CANDIDATES if res[c]["eligible"]]
        chosen = max(elig, key=lambda c: res[c]["sharpe"]) if elig else None
        out = {"protocol": "research/PROTOCOL_R4.md", "missing_symbols": missing, "design": {"period": [start.isoformat(), end.isoformat()],
               "candidates": res, "benchmarks": bench}, "chosen": chosen, "generated_at": datetime.now(timezone.utc).isoformat()}
    else:
        out = json.load(open(OUT))
        m = res[cids[0]]
        if mode == "holdout":
            ew = bench["equal_weight_top20"]["max_drawdown"]
            m["pass"] = bool(m["cagr"] > 0 and m["sharpe"] and m["sharpe"] >= 0.5 and m["max_drawdown"] >= -0.35 and m["max_drawdown"] > ew)
        out[mode] = {"period": [start.isoformat(), end.isoformat()], "candidate": cids[0], "result": m, "benchmarks": bench,
                     "note": "already-seen data (rounds 1-3); context only, not evidence" if mode == "context" else "unseen; run once"}
    json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps({"missing": missing, "results": res, "benchmarks": bench, "chosen": out.get("chosen")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
