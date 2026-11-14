"""Event-driven backtest of the signal engine. Kept strictly separate from paper and prospective (live) results.

No look-ahead / repainting: at bar i the engine receives only candles that closed at or before bar i (it is
called on a slice that ends at bar i, with `now` = that bar's close). SMC swings are confirmed k bars later by
construction. Fills can only happen on candles that open after the decision (plus `latency_bars`).

Fills and exits reuse app.signals.lifecycle.track (worse-edge fills, conservative same-candle rule, thirds at
TP1/TP2/TP3). If a resolver is supplied (e.g. 1-minute candles), same-candle stop/target collisions are resolved
with it; otherwise the stop is assumed first.

Costs: fee + slippage per side (from the strategy config, already in the signal), plus Futures funding charged
at `funding_rate_8h` for the time in the trade (longs pay when positive). Results are in R and as an equity
curve with fixed-fractional risk per trade (compounded).

One position at a time per backtest; a new setup is only taken after the previous one has exited, expired or
been invalidated. Trades still open when the data ends are reported separately, not counted.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ..providers.base import INTERVAL_MS
from ..signals.engine import evaluate
from ..signals.lifecycle import track
from ..signals.strategy import StrategyConfig

WINDOW = 300


def _dt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _slice(s, a, b):
    return {k: s[k][a:b] for k in ("t", "o", "h", "l", "c", "v")}


class Backtest:
    def __init__(self, series, htf, cfg: StrategyConfig, *, symbol: str, market: str, source: str,
                 latency_bars: int = 0, funding_rate_8h: float = 0.0, resolver=None):
        self.s, self.htf, self.cfg = series, htf, cfg
        self.symbol, self.market, self.source = symbol, market, source
        self.latency, self.funding, self.resolver = latency_bars, funding_rate_8h, resolver
        self.step = INTERVAL_MS[cfg.timeframe]
        self.n = len(series["t"])
        self.loose = replace(cfg, min_score=0, min_rr=-1e9)    # thresholds applied later (walk-forward selects them)
        self._cands: dict[int, dict] | None = None
        self._outcomes: dict[int, dict] = {}
        self.end = _dt(series["t"][-1] + self.step + 1) if self.n else None
        self.t_index = {t: i for i, t in enumerate(series["t"])}

    # ---- 1. candidate setups, decided bar by bar with closed data only ----
    def candidates(self) -> dict[int, dict]:
        if self._cands is not None:
            return self._cands
        out = {}
        for i in range(self.cfg.min_bars - 1, self.n):
            a = max(0, i + 1 - WINDOW)
            win = _slice(self.s, a, i + 1)
            gaps = sum(max(0, round((y - x) / self.step) - 1) for x, y in zip(win["t"], win["t"][1:]))
            now = _dt(self.s["t"][i] + self.step + 1000)       # 1s after the bar closed
            r = evaluate(win, self.htf, symbol=self.symbol, market=self.market, source=self.source,
                         cfg=self.loose, now=now, gaps=gaps)
            if r["side"] in ("LONG", "SHORT"):
                r["bar_index"] = i
                out[i] = r
        self._cands = out
        return out

    # ---- 2. outcome of one candidate (lazy) ----
    def outcome(self, i: int) -> dict:
        if i in self._outcomes:
            return self._outcomes[i]
        sig = dict(self._cands[i])
        if self.latency:
            sig["data_as_of"] = _dt(datetime.fromisoformat(sig["data_as_of"]).timestamp() * 1000 + self.latency * self.step).isoformat()
        res = track(sig, self.s, self.end, resolver=self.resolver)
        ev = res["events"]
        last_i = self.t_index.get(datetime.fromisoformat(ev[-1]["at"]).timestamp() * 1000 - self.step) if ev else None
        trade = None
        if res["terminal"] and res["outcome"]:
            o = res["outcome"]
            t_in = datetime.fromisoformat(ev[0]["at"]) - timedelta(milliseconds=self.step)
            t_out = datetime.fromisoformat(ev[-1]["at"])
            hours = (t_out - t_in).total_seconds() / 3600
            risk = abs(o["fill"] - sig["stop"])
            funding_r = 0.0
            if self.market == "futures" and self.funding:
                funding_r = o["fill"] * self.funding * hours / 8 / risk * (1 if sig["side"] == "LONG" else -1)
            trade = {"bar_index": i, "signal_time": sig["data_as_of"], "entry_time": t_in.isoformat(), "exit_time": t_out.isoformat(),
                     "side": sig["side"], "symbol": self.symbol, "regime": sig.get("regime"), "score": sig["score"],
                     "rr_net_planned": sig["rr_net"], "exit": o["exit"], "targets_hit": o["targets_hit"],
                     "gross_r": o["gross_r"], "net_r": round(o["net_r"] - funding_r, 6), "funding_r": round(funding_r, 6),
                     "hours": round(hours, 2), "ambiguous": any(e["detail"].get("ambiguous_same_candle") for e in ev),
                     "resolved_1m": any(e["detail"].get("resolved_with") or e["detail"].get("rule") == "order resolved with 1m candles" for e in ev)}
        self._outcomes[i] = {"terminal": res["terminal"], "lifecycle": res["lifecycle"], "last_index": last_i, "trade": trade}
        return self._outcomes[i]

    # ---- 3. sequential simulation with thresholds over a bar range ----
    def simulate(self, min_score: float, min_rr: float, a: int = 0, b: int | None = None) -> dict:
        b = self.n if b is None else b
        cands = self.candidates()
        trades, open_at_end, unfilled, blocked = [], 0, 0, -1
        for i in range(a, b):
            if i <= blocked or i not in cands:
                continue
            c = cands[i]
            if c["score"] < min_score or c["rr_net"] < min_rr:
                continue
            o = self.outcome(i)
            if not o["terminal"]:
                open_at_end += 1
                break
            if o["trade"]:
                trades.append(o["trade"])
            else:
                unfilled += 1
            blocked = o["last_index"] if o["last_index"] is not None else i
        return {"trades": trades, "open_at_end": open_at_end, "unfilled_setups": unfilled}


# ---------------- metrics ----------------
def metrics(trades: list[dict], risk_pct: float = 1.0) -> dict:
    n = len(trades)
    rs = [t["net_r"] for t in trades]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r < 0]
    eq, peak, mdd, curve = 1.0, 1.0, 0.0, []
    streak = worst = 0
    for t in trades:
        eq *= 1 + t["net_r"] * risk_pct / 100
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
        curve.append({"time": t["exit_time"], "equity": round(eq, 6)})
        streak = streak + 1 if t["net_r"] < 0 else 0
        worst = max(worst, streak)
    gross_win, gross_loss = sum(wins), -sum(losses)

    def group(key):
        g = defaultdict(list)
        for t in trades:
            g[key(t)].append(t["net_r"])
        return {k: {"trades": len(v), "win_rate": round(sum(1 for r in v if r > 0) / len(v), 4), "total_r": round(sum(v), 4),
                    "avg_r": round(sum(v) / len(v), 4)} for k, v in sorted(g.items())}

    warnings = []
    if n < 30:
        warnings.append(f"Only {n} trades — too few for reliable statistics. Treat these numbers as anecdotal.")
    return {
        "trades": n, "wins": len(wins), "losses": len(losses), "breakeven": n - len(wins) - len(losses),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "avg_r": round(sum(rs) / n, 4) if n else None, "expectancy_r": round(sum(rs) / n, 4) if n else None,
        "avg_win_r": round(gross_win / len(wins), 4) if wins else None, "avg_loss_r": round(-gross_loss / len(losses), 4) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
        "total_r": round(sum(rs), 4), "risk_per_trade_pct": risk_pct,
        "net_pnl_pct": round((eq - 1) * 100, 4), "max_drawdown_pct": round(mdd * 100, 4), "max_consecutive_losses": worst,
        "equity_curve": curve,
        "by_side": group(lambda t: t["side"]), "by_exit": group(lambda t: t["exit"]),
        "by_regime": group(lambda t: t.get("regime") or "unknown"), "by_month": group(lambda t: t["exit_time"][:7]),
        "ambiguous_candles": sum(1 for t in trades if t.get("ambiguous")),
        "warnings": warnings,
    }


# ---------------- splits & walk-forward ----------------
GRID = [(s, r) for s in (55, 60, 65, 70) for r in (1.5, 2.0, 2.5)]


def chronological_splits(bt: Backtest, cfg: StrategyConfig, fractions=(0.6, 0.2, 0.2), risk_pct=1.0) -> dict:
    n = bt.n
    first = cfg.min_bars - 1
    usable = n - first
    a = first + int(usable * fractions[0])
    b = a + int(usable * fractions[1])
    out = {}
    for name, (lo, hi) in {"development": (first, a), "validation": (a, b), "out_of_sample": (b, n)}.items():
        sim = bt.simulate(cfg.min_score, cfg.min_rr, lo, hi)
        out[name] = {"from": _dt(bt.s["t"][lo]).isoformat() if lo < n else None, "to": _dt(bt.s["t"][hi - 1] + bt.step).isoformat() if hi > lo else None,
                     "bars": hi - lo, **{k: v for k, v in sim.items() if k != "trades"}, "metrics": metrics(sim["trades"], risk_pct)}
    out["out_of_sample"]["note"] = ("Untouched period: the strategy configuration was fixed before this period was evaluated "
                                    "and nothing was tuned on it.")
    return out


def walk_forward(bt: Backtest, cfg: StrategyConfig, train_bars: int, test_bars: int, min_train_trades: int = 5, risk_pct=1.0) -> dict:
    """Rolling windows: choose (min_score, min_rr) from GRID on the train window by expectancy (needs ≥ min_train_trades,
    else keep the config defaults), then apply them unchanged to the next test window. Only test windows are reported."""
    folds, oos_trades = [], []
    start = cfg.min_bars - 1
    while start + train_bars + test_bars <= bt.n:
        tr = (start, start + train_bars)
        te = (tr[1], tr[1] + test_bars)
        best, best_e = (cfg.min_score, cfg.min_rr), -math.inf
        for s, r in GRID:
            sim = bt.simulate(s, r, *tr)
            if len(sim["trades"]) >= min_train_trades:
                e = sum(t["net_r"] for t in sim["trades"]) / len(sim["trades"])
                if e > best_e:
                    best, best_e = (s, r), e
        test = bt.simulate(best[0], best[1], *te)
        oos_trades += test["trades"]
        folds.append({"train_from": _dt(bt.s["t"][tr[0]]).isoformat(), "train_to": _dt(bt.s["t"][tr[1] - 1] + bt.step).isoformat(),
                      "test_from": _dt(bt.s["t"][te[0]]).isoformat(), "test_to": _dt(bt.s["t"][te[1] - 1] + bt.step).isoformat(),
                      "chosen_min_score": best[0], "chosen_min_rr": best[1],
                      "train_expectancy_r": None if best_e == -math.inf else round(best_e, 4),
                      "test_trades": len(test["trades"]), "test_total_r": round(sum(t["net_r"] for t in test["trades"]), 4)})
        start += test_bars
    return {"folds": folds, "grid": GRID, "out_of_sample_metrics": metrics(oos_trades, risk_pct),
            "note": "Only the test windows are reported; each test window was unseen when its thresholds were chosen."}


def run(series, htf, cfg: StrategyConfig, *, symbol, market, source, latency_bars=0, funding_rate_8h=0.0,
        resolver=None, risk_pct=1.0, train_bars=None, test_bars=None) -> dict:
    bt = Backtest(series, htf, cfg, symbol=symbol, market=market, source=source, latency_bars=latency_bars,
                  funding_rate_8h=funding_rate_8h, resolver=resolver)
    full = bt.simulate(cfg.min_score, cfg.min_rr)
    usable = bt.n - (cfg.min_bars - 1)
    train_bars = train_bars or max(100, usable // 3)
    test_bars = test_bars or max(50, usable // 6)
    return {
        "kind": "backtest", "symbol": symbol, "market": market, "timeframe": cfg.timeframe, "strategy": cfg.name,
        "strategy_version": cfg.version, "config": cfg.snapshot(), "config_hash": cfg.hash(), "data_source": source,
        "data_from": _dt(series["t"][0]).isoformat() if bt.n else None, "data_to": _dt(series["t"][-1] + bt.step).isoformat() if bt.n else None,
        "bars": bt.n, "candidate_setups": len(bt.candidates()),
        "assumptions": {"fee_rate_per_side": cfg.fee_rate.get(market), "slippage_per_side": cfg.slippage,
                        "funding_rate_8h": funding_rate_8h if market == "futures" else 0, "latency_bars": latency_bars,
                        "same_candle_rule": "1m candles when available, otherwise stop first" if resolver else "stop first",
                        "exits": "thirds at TP1/TP2/TP3; remainder at stop or time exit", "risk_per_trade_pct": risk_pct,
                        "positions": "one at a time"},
        "full_period": {**{k: v for k, v in full.items() if k != "trades"}, "metrics": metrics(full["trades"], risk_pct)},
        "splits": chronological_splits(bt, cfg, risk_pct=risk_pct),
        "walk_forward": walk_forward(bt, cfg, train_bars, test_bars, risk_pct=risk_pct),
        "trades": full["trades"],
        "disclaimer": "Backtest on historical data under the stated assumptions. Past results don't predict future results; "
                      "this is not a measure of live accuracy.",
    }
