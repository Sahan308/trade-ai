"""Run a backtest on real historical data and store it.

    python -m app.backtest --symbol BTCUSDT --market spot --days 180 [--profile day] [--latency 0]
                           [--funding 0.0001] [--risk 1] [--no-1m] [--no-store]
"""
import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..db import get_session
from ..models import BacktestRun
from ..providers.base import INTERVAL_MS, MarketType, ProviderError
from ..signals.strategy import PROFILES
from .core import run


def to_series(cs):
    return {"t": [x.open_time.timestamp() * 1000 for x in cs], "o": [x.open for x in cs], "h": [x.high for x in cs],
            "l": [x.low for x in cs], "c": [x.close for x in cs], "v": [x.volume for x in cs]}


def minute_resolver(provider, market, symbol):
    """Replay 1m candles inside an ambiguous candle to see whether the stop or a target was reached first."""
    def resolve(open_ms, step_ms, side, stop, targets):
        try:
            cs = provider.history(market, symbol, "1m", int(open_ms), int(open_ms + step_ms)).candles
        except ProviderError:
            return None
        for c in cs:
            stop_hit = c.low <= stop if side == "LONG" else c.high >= stop
            tp_hit = any((c.high >= t if side == "LONG" else c.low <= t) for t in targets)
            if stop_hit and tp_hit:
                return None          # still ambiguous at 1m → caller assumes the stop
            if tp_hit:
                return "target_first"
            if stop_hit:
                return "stop_first"
        return None
    return resolve



def backtest(provider, symbol, market, days, profile="day", latency=0, funding=None, risk=1.0, use_1m=True, now=None):
    cfg = PROFILES[profile]
    now = now or datetime.now(timezone.utc)
    mkt = MarketType(market)
    step = INTERVAL_MS[cfg.timeframe]
    end = int(now.timestamp() * 1000) // step * step                    # exclude the forming candle
    start = end - int(timedelta(days=days).total_seconds() * 1000) - cfg.min_bars * step
    ltf = provider.history(mkt, symbol, cfg.timeframe, start, end)
    htf_step = INTERVAL_MS[cfg.htf]
    htf = provider.history(mkt, symbol, cfg.htf, start - 60 * htf_step, end)
    funding = (0.0001 if market == "futures" else 0.0) if funding is None else funding
    res = run(to_series(ltf.candles), to_series(htf.candles), cfg, symbol=symbol.upper(), market=market, source=ltf.source,
              latency_bars=latency, funding_rate_8h=funding, resolver=minute_resolver(provider, mkt, symbol) if use_1m else None,
              risk_pct=risk)
    res["data_gaps"] = ltf.gaps
    return res


def store(result) -> str:
    session = next(get_session())
    try:
        row = BacktestRun(id=str(uuid.uuid4()), kind="backtest", symbol=result["symbol"], market=result["market"],
                          timeframe=result["timeframe"], strategy=result["strategy"], strategy_version=result["strategy_version"],
                          config_hash=result["config_hash"], data_from=datetime.fromisoformat(result["data_from"]),
                          data_to=datetime.fromisoformat(result["data_to"]), result=result)
        session.add(row)
        session.commit()
        return row.id
    finally:
        session.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--market", default="spot", choices=["spot", "futures"])
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--profile", default="day", choices=sorted(PROFILES))
    ap.add_argument("--latency", type=int, default=0, help="extra candles before a fill is allowed")
    ap.add_argument("--funding", type=float, default=None, help="assumed funding per 8h for futures (default 0.0001)")
    ap.add_argument("--risk", type=float, default=1.0, help="risk per trade in %% for the equity curve")
    ap.add_argument("--no-1m", action="store_true", help="don't use 1m candles to resolve same-candle collisions")
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args()
    from ..main import default_provider
    res = backtest(default_provider(get_settings()), a.symbol, a.market, a.days, a.profile, a.latency, a.funding, a.risk, not a.no_1m)
    m = res["full_period"]["metrics"]
    summary = {k: m[k] for k in ("trades", "win_rate", "profit_factor", "expectancy_r", "net_pnl_pct", "max_drawdown_pct", "warnings")}
    summary["out_of_sample"] = {k: res["splits"]["out_of_sample"]["metrics"][k] for k in ("trades", "expectancy_r", "total_r")}
    summary["walk_forward_oos"] = {k: res["walk_forward"]["out_of_sample_metrics"][k] for k in ("trades", "expectancy_r", "total_r")}
    summary.update(source=res["data_source"], bars=res["bars"], data_from=res["data_from"], data_to=res["data_to"])
    if not a.no_store:
        summary["stored_id"] = store(res)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
