"""Round-3 research harness: different strategy families. Follows research/PROTOCOL_R3.md exactly.

    python research/run_r3.py design  <data_dir>   # design period only -> research/design_results_r3.json
    python research/run_r3.py holdout <data_dir>   # ONCE, only the candidate chosen in the design run

Pure Python (no third-party packages). The design run never reads a candle that closes on or after HOLDOUT_START.
"""
import gzip
import json
import os
import sys
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT"]
DESIGN_START = datetime(2023, 11, 15, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2025, 11, 15, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 11, 14, tzinfo=timezone.utc)
COST = 0.0010 + 0.0005            # fee + slippage per side
TF_MS = {"1D": 86_400_000, "4H": 14_400_000}
OUT = os.path.join(os.path.dirname(__file__), "design_results_r3.json")
MS = lambda d: int(d.timestamp() * 1000)  # noqa: E731


# ---------- indicators (value at index i uses candles 0..i only) ----------
def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def atr(h, l, c, n):
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    out, a = [None] * len(c), None
    for i, v in enumerate(tr):
        if i == n - 1:
            a = sum(tr[:n]) / n
        elif i >= n:
            a = (a * (n - 1) + v) / n
        out[i] = a if i >= n - 1 else None
    return out


def rsi(c, n):
    out, ag, al = [None] * len(c), 0.0, 0.0
    for i in range(1, len(c)):
        g, lo = max(c[i] - c[i - 1], 0), max(c[i - 1] - c[i], 0)
        if i <= n:
            ag += g / n; al += lo / n
            if i == n:
                out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        else:
            ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + lo) / n
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def stdev(x, n):
    m, out = sma(x, n), [None] * len(x)
    for i in range(n - 1, len(x)):
        mu = m[i]
        out[i] = (sum((v - mu) ** 2 for v in x[i - n + 1:i + 1]) / n) ** 0.5
    return out


def hh(h, n):  # highest high of the previous n candles (excluding i)
    return [max(h[i - n:i]) if i >= n else None for i in range(len(h))]


def ll(l, n):
    return [min(l[i - n:i]) if i >= n else None for i in range(len(l))]


# ---------- candidates: return per-index entry/exit booleans and an optional stop distance ----------
def cand(cid, d):
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    E, X, stop, maxhold = [False] * n, [False] * n, [None] * n, None
    if cid in ("T1", "T2"):
        ne, nx = (20, 10) if cid == "T1" else (55, 20)
        up, dn, a = hh(h, ne), ll(l, nx), atr(h, l, c, 20)
        for i in range(n):
            if up[i] is not None and a[i] is not None and c[i] > up[i]:
                E[i] = True; stop[i] = 2 * a[i]
            if dn[i] is not None and c[i] < dn[i]:
                X[i] = True
    elif cid == "T3":
        m = sma(c, 100)
        for i in range(n):
            if m[i] is not None:
                E[i], X[i] = c[i] > m[i], c[i] < m[i]
    elif cid == "T4":
        f, s = sma(c, 50), sma(c, 200)
        for i in range(1, n):
            if None not in (f[i], s[i], f[i - 1], s[i - 1]):
                E[i] = f[i - 1] <= s[i - 1] and f[i] > s[i]
                X[i] = f[i - 1] >= s[i - 1] and f[i] < s[i]
    elif cid == "M1":
        r, s200, s5 = rsi(c, 2), sma(c, 200), sma(c, 5)
        maxhold = 10
        for i in range(n):
            if None not in (r[i], s200[i]):
                E[i] = r[i] < 10 and c[i] > s200[i]
            if s5[i] is not None:
                X[i] = c[i] > s5[i]
    elif cid == "M2":
        mid, sd, s200, a = sma(c, 20), stdev(c, 20), sma(c, 200), atr(h, l, c, 14)
        maxhold = 30
        for i in range(n):
            if None not in (mid[i], sd[i], s200[i], a[i]):
                E[i] = c[i] < mid[i] - 2 * sd[i] and c[i] > s200[i]
                X[i] = c[i] >= mid[i]
                stop[i] = 2 * a[i]
    return E, X, stop, maxhold


TF = {"T1": "1D", "T2": "1D", "T3": "1D", "T4": "1D", "M1": "1D", "M2": "4H"}
CANDIDATES = list(TF)


def simulate(d, cid, trade_from, trade_to):
    """Signal on close of candle i, fill at open of i+1. Trades are opened only for fills in [trade_from, trade_to);
    open positions are closed at the last candle's close of the window."""
    E, X, stop, maxhold = cand(cid, d)
    t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]
    trades, pos = [], None
    for i in range(len(c) - 1):
        j = i + 1                       # execution candle
        if t[j] >= trade_to:
            break
        if pos is not None:
            # stop check on candle j happens before acting on signals from candle i? No: signals from i fill at open j,
            # then candle j can hit the stop. Handle the exit-signal fill first (it happens at the open).
            pass
        if pos is not None and (X[i] or (maxhold and i - pos["i"] + 1 >= maxhold)):
            px = o[j] * (1 - COST)
            trades.append(dict(entry_t=pos["t"], exit_t=t[j], ret=px / pos["px"] - 1, why="exit"))
            pos = None
        elif pos is None and E[i] and t[j] >= trade_from:
            pos = dict(i=j, t=t[j], px=o[j] * (1 + COST),
                       stop=(o[j] - stop[i]) if stop[i] else None)
        if pos is not None and pos["stop"] is not None and l[j] <= pos["stop"]:
            fill = min(o[j], pos["stop"]) if j != pos["i"] else pos["stop"]
            trades.append(dict(entry_t=pos["t"], exit_t=t[j], ret=fill * (1 - COST) / pos["px"] - 1, why="stop"))
            pos = None
    if pos is not None:
        k = max(i for i in range(len(c)) if t[i] < trade_to)
        trades.append(dict(entry_t=pos["t"], exit_t=t[k], ret=c[k] * (1 - COST) / pos["px"] - 1, why="window_end"))
    return trades


def load(data_dir, sym, tf, end):
    d = json.load(gzip.open(os.path.join(data_dir, f"{sym}_{tf}.json.gz"), "rt"))
    keep = [i for i, t in enumerate(d["t"]) if t + TF_MS[tf] <= MS(end)]       # only candles that closed before `end`
    return {k: [d[k][i] for i in keep] for k in ("t", "o", "h", "l", "c")}


def stats(trades):
    r = [x["ret"] for x in trades]
    wins, losses = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
    return dict(trades=len(r), win_rate=round(sum(x > 0 for x in r) / len(r), 4) if r else None,
                mean_ret=round(sum(r) / len(r), 5) if r else None,
                profit_factor=round(wins / losses, 3) if losses > 0 else (None if not r else float("inf")),
                gross_profit=round(wins, 5))


def bh(data, start, end, tf):
    out = []
    for sym, d in data.items():
        idx = [i for i, t in enumerate(d["t"]) if MS(start) <= t < MS(end)]
        if idx:
            out.append(d["c"][idx[-1]] / d["o"][idx[0]] - 1)
    return round(sum(out) / len(out), 4) if out else None


def run(mode, data_dir):
    if mode == "design":
        start, end = DESIGN_START, HOLDOUT_START
        cids = CANDIDATES
    else:
        chosen = json.load(open(OUT)).get("chosen")
        if not chosen:
            sys.exit("No eligible candidate was chosen in the design run: the holdout stays unused (protocol).")
        start, end, cids = HOLDOUT_START, HOLDOUT_END, [chosen]
    halves = [(DESIGN_START, datetime(2024, 5, 15, tzinfo=timezone.utc)), (datetime(2024, 5, 15, tzinfo=timezone.utc), datetime(2024, 11, 15, tzinfo=timezone.utc)),
              (datetime(2024, 11, 15, tzinfo=timezone.utc), datetime(2025, 5, 15, tzinfo=timezone.utc)), (datetime(2025, 5, 15, tzinfo=timezone.utc), HOLDOUT_START)]
    res = {}
    for cid in cids:
        tf = TF[cid]
        # holdout: indicators may use earlier candles for warm-up, but trades only open inside the holdout year
        data = {s: load(data_dir, s, tf, end) for s in SYMBOLS}
        all_t, per_sym = [], {}
        for s, d in data.items():
            tr = simulate(d, cid, MS(start), MS(end))
            per_sym[s] = stats(tr); all_t += [dict(x, sym=s) for x in tr]
        r = stats(all_t)
        r["per_symbol"] = per_sym
        r["buy_and_hold_equal_weight"] = bh(data, start, end, tf)
        if mode == "design":
            hv = []
            for a, b in halves:
                sub = [x for x in all_t if MS(a) <= x["entry_t"] < MS(b)]
                hv.append(round(sum(x["ret"] for x in sub) / len(sub), 5) if sub else None)
            r["half_year_mean_ret"] = hv
            with_trades = [v for v in hv if v is not None]
            r["eligible"] = bool(r["trades"] >= 60 and r["profit_factor"] and r["profit_factor"] >= 1.2 and r["mean_ret"] > 0
                                 and sum(v > 0 for v in with_trades) >= min(3, len(with_trades)) and len(with_trades) >= 3)
        else:
            gp = {s: sum(x["ret"] for x in all_t if x["sym"] == s and x["ret"] > 0) for s in SYMBOLS}
            tot = sum(gp.values())
            r["max_symbol_share_of_gross_profit"] = round(max(gp.values()) / tot, 3) if tot > 0 else None
            r["pass"] = bool(r["trades"] >= 30 and r["mean_ret"] and r["mean_ret"] > 0 and r["profit_factor"] and r["profit_factor"] >= 1.1
                             and r["max_symbol_share_of_gross_profit"] is not None and r["max_symbol_share_of_gross_profit"] <= 0.5)
        res[cid] = r
    if mode == "design":
        elig = [c for c in CANDIDATES if res[c]["eligible"]]
        chosen = max(elig, key=lambda c: res[c]["mean_ret"]) if elig else None
        out = {"protocol": "research/PROTOCOL_R3.md", "period": [DESIGN_START.isoformat(), HOLDOUT_START.isoformat()],
               "cost_per_side": COST, "results": res, "chosen": chosen,
               "generated_at": datetime.now(timezone.utc).isoformat()}
        json.dump(out, open(OUT, "w"), indent=2)
    else:
        out = json.load(open(OUT)); out["holdout"] = {"period": [HOLDOUT_START.isoformat(), HOLDOUT_END.isoformat()], **res[cids[0]], "candidate": cids[0]}
        json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps({c: {k: v for k, v in r.items() if k != "per_symbol"} for c, r in res.items()}, indent=1))
    if mode == "design":
        print("chosen:", out["chosen"])


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
