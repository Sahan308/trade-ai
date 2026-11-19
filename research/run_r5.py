"""Round-5: many candidate signal systems, fixed rules, no tuning. See research/PROTOCOL_R5.md.

    python3 run_r5.py fetch <data_dir>
    python3 run_r5.py test  <data_dir>     -> design_results_r5.json

Every system emits per-coin trades with entry / stop / exit like the website's signals.
Signal on a closed bar, entry at the NEXT bar's open, stop checked on highs/lows (stop wins if
both stop and target are touched in one bar). Results are in R (1R = entry-to-stop distance);
costs 0.15% round trip (fees + slippage) converted into R per trade.
"""
import gzip, json, math, os, sys, time, urllib.request
from datetime import datetime, timezone

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "TRXUSDT", "XLMUSDT",
           "ETCUSDT", "BCHUSDT", "ATOMUSDT", "SOLUSDT", "DOTUSDT", "AVAXUSDT", "UNIUSDT", "FILUSDT", "NEARUSDT", "AAVEUSDT"]
COST = 0.0015
MS = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)  # noqa
PERIODS = {"A_2020_2023": (MS(2020, 1, 1), MS(2024, 1, 1)), "B_2024_2026": (MS(2024, 1, 1), MS(2026, 11, 19))}


def fetch(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    for s in SYMBOLS:
        for iv in ("1d", "4h"):
            p = os.path.join(data_dir, f"{s}_{iv}.json.gz")
            if os.path.exists(p):
                continue
            rows, start = [], MS(2019, 6, 1)
            while True:
                u = f"https://data-api.binance.vision/api/v3/klines?symbol={s}&interval={iv}&startTime={start}&limit=1000"
                for a in range(5):
                    try:
                        batch = json.load(urllib.request.urlopen(u, timeout=30)); break
                    except Exception:
                        time.sleep(2 + a * 3)
                else:
                    raise SystemExit(f"fetch failed {s} {iv}")
                if not batch:
                    break
                rows += batch
                start = batch[-1][0] + 1
                if len(batch) < 1000:
                    break
            now = time.time() * 1000
            step = 86_400_000 if iv == "1d" else 14_400_000
            rows = [r for r in rows if r[0] + step <= now]  # closed bars only
            d = {k: [float(r[i]) for r in rows] for k, i in (("o", 1), ("h", 2), ("l", 3), ("c", 4), ("v", 5))}
            d["t"] = [r[0] for r in rows]
            json.dump(d, gzip.open(p, "wt"))
            print(s, iv, len(rows), flush=True)


def load(data_dir, iv):
    out = {}
    for s in SYMBOLS:
        p = os.path.join(data_dir, f"{s}_{iv}.json.gz")
        if os.path.exists(p):
            out[s] = json.load(gzip.open(p, "rt"))
    return out


# ---------- indicators ----------
def sma(x, n):
    o, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n: s -= x[i - n]
        if i >= n - 1: o[i] = s / n
    return o


def ema(x, n):
    o, k, e = [None] * len(x), 2 / (n + 1), None
    for i, v in enumerate(x):
        e = v if e is None else e + k * (v - e)
        if i >= n - 1: o[i] = e
    return o


def atr(d, n=14):
    h, l, c = d["h"], d["l"], d["c"]
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    o, a = [None] * len(c), None
    for i, v in enumerate(tr):
        a = v if a is None else a + (v - a) / n
        if i >= n: o[i] = a
    return o


def rsi(c, n):
    o, ag, al = [None] * len(c), 0.0, 0.0
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]
        g, l = max(ch, 0), max(-ch, 0)
        if i <= n:
            ag += g / n; al += l / n
        else:
            ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n
        if i >= n: o[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return o


def hh(x, n, i): return max(x[i - n + 1:i + 1])
def ll(x, n, i): return min(x[i - n + 1:i + 1])


# ---------- generic trade engine ----------
def run_trades(d, entries, max_bars):
    """entries: dict bar_index -> (side, stop, target_or_None, exit_rule) ; exit_rule(j, side) -> bool (close-based exit)."""
    o, h, l, c, t = d["o"], d["h"], d["l"], d["c"], d["t"]
    trades, busy_until = [], -1
    for i in sorted(entries):
        if i <= busy_until or i + 1 >= len(c):
            continue
        side, stop, tgt, rule = entries[i]
        e = o[i + 1]
        risk = (e - stop) if side > 0 else (stop - e)
        if risk <= 0 or risk / e < 0.003:
            continue
        r, j = None, i + 1
        while j < len(c) and j <= i + max_bars:
            if side > 0:
                if l[j] <= stop: r = (min(o[j], stop) - e) / risk; break
                if tgt and h[j] >= tgt: r = (max(o[j], tgt) - e) / risk; break
            else:
                if h[j] >= stop: r = (e - max(o[j], stop)) / risk; break
                if tgt and l[j] <= tgt: r = (e - min(o[j], tgt)) / risk; break
            if rule and rule(j, side):
                r = side * (c[j] - e) / risk; break
            j += 1
        if r is None:
            j = min(j, len(c) - 1)
            if j == len(c) - 1 and j < i + max_bars:
                continue  # still open at end of data: not scored
            r = side * (c[j] - e) / risk
        r -= COST * e / risk
        trades.append({"t": t[i + 1], "r": r})
        busy_until = j
    return trades


# ---------- systems ----------
def btc_regime(btc1d):
    s200 = sma(btc1d["c"], 200)
    return {btc1d["t"][i]: (s200[i] is not None and btc1d["c"][i] > s200[i]) for i in range(len(btc1d["c"]))}


def day_of(t): return t - t % 86_400_000


def regime_ok(reg, t, step):
    # regime known as of the last CLOSED daily bar before this bar closes
    return reg.get(day_of(t + step) - 86_400_000, False)


def S1_donchian20(d, ctx):  # daily 20-bar breakout long, 2 ATR stop, exit on 10-bar low
    c, a, E = d["c"], atr(d), {}
    for i in range(25, len(c)):
        if a[i] and c[i] > hh(c, 20, i - 1):
            E[i] = (1, c[i] - 2 * a[i], None, lambda j, s, c=c: c[j] < ll(c, 10, j - 1))
    return run_trades(d, E, 120)


def S2_donchian20_regime(d, ctx):  # S1 only when BTC is above its 200-day average
    c, a, E = d["c"], atr(d), {}
    for i in range(25, len(c)):
        if a[i] and c[i] > hh(c, 20, i - 1) and regime_ok(ctx["reg"], d["t"][i], 86_400_000):
            E[i] = (1, c[i] - 2 * a[i], None, lambda j, s, c=c: c[j] < ll(c, 10, j - 1))
    return run_trades(d, E, 120)


def S3_turtle55(d, ctx):  # daily 55-bar breakout long/short, 2 ATR stop, exit on 20-bar opposite
    c, a, E = d["c"], atr(d), {}
    for i in range(60, len(c)):
        if not a[i]: continue
        if c[i] > hh(c, 55, i - 1):
            E[i] = (1, c[i] - 2 * a[i], None, lambda j, s, c=c: c[j] < ll(c, 20, j - 1))
        elif c[i] < ll(c, 55, i - 1):
            E[i] = (-1, c[i] + 2 * a[i], None, lambda j, s, c=c: c[j] > hh(c, 20, j - 1))
    return run_trades(d, E, 200)


def S4_rsi2_dip(d, ctx):  # daily: uptrend (close>200SMA) and RSI2<10 -> buy; exit close>5SMA; 3 ATR stop
    c, a, r2, s200, s5, E = d["c"], atr(d), rsi(d["c"], 2), sma(d["c"], 200), sma(d["c"], 5), {}
    for i in range(201, len(c)):
        if a[i] and s200[i] and c[i] > s200[i] and r2[i] is not None and r2[i] < 10:
            E[i] = (1, c[i] - 3 * a[i], None, lambda j, s, c=c, s5=s5: c[j] > s5[j])
    return run_trades(d, E, 10)


def S5_ema_pullback_4h(d, ctx):  # 4h: EMA50>EMA200, close dips to EMA20 then closes back above; 1.5ATR stop, 3ATR target
    c, l, a, e20, e50, e200, E = d["c"], d["l"], atr(d), ema(d["c"], 20), ema(d["c"], 50), ema(d["c"], 200), {}
    for i in range(201, len(c)):
        if a[i] and e50[i] > e200[i] and l[i] <= e20[i] < c[i] and c[i - 1] > e20[i - 1]:
            E[i] = (1, c[i] - 1.5 * a[i], c[i] + 3 * a[i], None)
    return run_trades(d, E, 60)


def S6_squeeze_4h(d, ctx):  # 4h Bollinger width at 120-bar low, then close outside band -> trade that way; 2ATR stop, exit at 20EMA cross
    c, a, m, E = d["c"], atr(d), sma(d["c"], 20), {}
    sd = [None] * len(c)
    for i in range(19, len(c)):
        w = c[i - 19:i + 1]; mu = sum(w) / 20
        sd[i] = math.sqrt(sum((x - mu) ** 2 for x in w) / 20)
    width = [(4 * sd[i] / m[i]) if sd[i] and m[i] else None for i in range(len(c))]
    e20 = ema(c, 20)
    for i in range(140, len(c)):
        ws = [w for w in width[i - 120:i] if w]
        if not a[i] or not ws or width[i - 1] is None or width[i - 1] > min(ws) * 1.1:
            continue
        up, dn = m[i] + 2 * sd[i], m[i] - 2 * sd[i]
        if c[i] > up:
            E[i] = (1, c[i] - 2 * a[i], None, lambda j, s, c=c, e=e20: c[j] < e[j])
        elif c[i] < dn:
            E[i] = (-1, c[i] + 2 * a[i], None, lambda j, s, c=c, e=e20: c[j] > e[j])
    return run_trades(d, E, 90)


def S7_tsmom_weekly(d, ctx):  # daily: on Mondays, 28-day return >0 and BTC regime on -> hold 7 days, 3 ATR stop
    c, a, E = d["c"], atr(d), {}
    for i in range(30, len(c)):
        dt = datetime.fromtimestamp(d["t"][i] / 1000, timezone.utc)
        if dt.weekday() == 6 and a[i] and c[i] > c[i - 28] and regime_ok(ctx["reg"], d["t"][i], 86_400_000):
            E[i] = (1, c[i] - 3 * a[i], None, None)
    return run_trades(d, E, 7)


def S8_macd_4h(d, ctx):  # 4h MACD cross up, price above EMA200, BTC regime on; 2ATR stop; exit on MACD cross down
    c, a, e200 = d["c"], atr(d), ema(d["c"], 200)
    f, s = ema(c, 12), ema(c, 26)
    macd = [(f[i] - s[i]) if f[i] is not None and s[i] is not None else 0 for i in range(len(c))]
    sig = ema(macd, 9)
    E = {}
    for i in range(210, len(c)):
        if a[i] and sig[i] and macd[i] > sig[i] and macd[i - 1] <= sig[i - 1] and c[i] > e200[i] \
                and regime_ok(ctx["reg"], d["t"][i], 14_400_000):
            E[i] = (1, c[i] - 2 * a[i], None, lambda j, sd, m=macd, g=sig: m[j] < g[j])
    return run_trades(d, E, 90)


def S9_donchian_4h_regime(d, ctx):  # 4h 55-bar breakout long with BTC regime on, 2.5ATR stop, exit 20-bar low
    c, a, E = d["c"], atr(d), {}
    for i in range(60, len(c)):
        if a[i] and c[i] > hh(c, 55, i - 1) and regime_ok(ctx["reg"], d["t"][i], 14_400_000):
            E[i] = (1, c[i] - 2.5 * a[i], None, lambda j, s, c=c: c[j] < ll(c, 20, j - 1))
    return run_trades(d, E, 180)


def S10_inside_bar_trend(d, ctx):  # daily inside bar inside an uptrend (close>50SMA>200SMA); buy break of its high; stop its low; target 2R
    o, h, l, c, s50, s200 = d["o"], d["h"], d["l"], d["c"], sma(d["c"], 50), sma(d["c"], 200)
    E = {}
    for i in range(201, len(c) - 1):
        if s200[i] and c[i] > s50[i] > s200[i] and h[i] < h[i - 1] and l[i] > l[i - 1]:
            # no peeking at bar i+1: enter at its open, stop under the inside bar, target 2x the bar's range
            E[i] = (1, l[i], c[i] + 2 * (h[i] - l[i]), None)
    return run_trades(d, E, 20)


SYSTEMS = {
    "S1 Daily 20-day breakout": ("1d", S1_donchian20),
    "S2 Daily 20-day breakout + BTC trend filter": ("1d", S2_donchian20_regime),
    "S3 Turtle 55-day long/short": ("1d", S3_turtle55),
    "S4 RSI-2 dip buy in uptrend": ("1d", S4_rsi2_dip),
    "S5 4h EMA pullback": ("4h", S5_ema_pullback_4h),
    "S6 4h volatility squeeze breakout": ("4h", S6_squeeze_4h),
    "S7 Weekly momentum + BTC filter": ("1d", S7_tsmom_weekly),
    "S8 4h MACD + trend + BTC filter": ("4h", S8_macd_4h),
    "S9 4h 55-bar breakout + BTC filter": ("4h", S9_donchian_4h_regime),
    "S10 Daily inside-bar breakout in uptrend": ("1d", S10_inside_bar_trend),
}


def stats(trades):
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    rs = [x["r"] for x in trades]
    wins = [r for r in rs if r > 0]
    gp, gl = sum(wins), -sum(r for r in rs if r <= 0)
    months = {}
    for x in trades:
        k = datetime.fromtimestamp(x["t"] / 1000, timezone.utc).strftime("%Y-%m")
        months[k] = months.get(k, 0) + x["r"]
    mv = list(months.values())
    mm = sum(mv) / len(mv)
    msd = math.sqrt(sum((v - mm) ** 2 for v in mv) / max(1, len(mv) - 1)) or 1e-9
    eq, peak, mdd = 0, 0, 0
    for x in sorted(trades, key=lambda z: z["t"]):
        eq += x["r"]; peak = max(peak, eq); mdd = max(mdd, peak - eq)
    return {"trades": n, "win_rate": round(len(wins) / n, 3), "avg_r": round(sum(rs) / n, 3), "total_r": round(sum(rs), 1),
            "profit_factor": round(gp / gl, 2) if gl else None, "max_dd_r": round(mdd, 1),
            "months": len(mv), "monthly_t": round(mm / (msd / math.sqrt(len(mv))), 2)}


def passes(s):
    return s.get("trades", 0) >= 100 and s["avg_r"] >= 0.10 and (s["profit_factor"] or 0) >= 1.2 and s["monthly_t"] >= 2.0


def test(data_dir):
    data = {"1d": load(data_dir, "1d"), "4h": load(data_dir, "4h")}
    ctx = {"reg": btc_regime(data["1d"]["BTCUSDT"])}
    res = {}
    for name, (iv, fn) in SYSTEMS.items():
        alltr = []
        for s, d in data[iv].items():
            alltr += fn(d, ctx)
        res[name] = {}
        for pn, (a, b) in PERIODS.items():
            res[name][pn] = stats([x for x in alltr if a <= x["t"] < b])
        res[name]["PASS"] = all(passes(res[name][p]) for p in PERIODS)
        print(name, json.dumps(res[name]), flush=True)
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "design_results_r5.json"), "w"), indent=1)


FORWARD_START = MS(2026, 11, 19)
FORWARD_SYSTEMS = list(SYSTEMS)  # all ten, frozen as written


def forward(data_dir):
    """Live paper test: the rules are frozen as of 2026-11-19, so re-running them on fresh closed candles
    and keeping only trades that ENTER after that date is the same as paper trading them in real time."""
    import shutil
    shutil.rmtree(data_dir, ignore_errors=True)
    fetch(data_dir)
    data = {"1d": load(data_dir, "1d"), "4h": load(data_dir, "4h")}
    ctx = {"reg": btc_regime(data["1d"]["BTCUSDT"])}
    out = {}
    for name in FORWARD_SYSTEMS:
        iv, fn = SYSTEMS[name]
        tr = []
        for s, d in data[iv].items():
            tr += [dict(x, sym=s) for x in fn(d, ctx) if x["t"] >= FORWARD_START]
        out[name] = {"closed": stats(tr), "trades": tr}
        print(name, json.dumps(out[name]["closed"]), flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "forward_r5.json"), "w"), indent=1)


if __name__ == "__main__":
    {"fetch": fetch, "test": test, "forward": forward}[sys.argv[1]](sys.argv[2])
