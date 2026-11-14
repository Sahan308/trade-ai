"""Performance reporting. Backtest, paper and prospective results are reported separately and never mixed."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..backtest.core import metrics
from ..db import get_session
from ..models import BacktestRun, Signal

router = APIRouter(prefix="/api", tags=["performance"])

KIND_NOTES = {
    "prospective": "Signals produced live by the scanner and tracked forward in time. Outcomes use the documented "
                   "lifecycle model (simulated fills and exits); fees and slippage included, funding excluded.",
    "paper": "Paper trading is not implemented yet.",
    "backtest": "Historical simulation. See each run's assumptions.",
}


@router.get("/performance", summary="Measured results for one result type")
def performance(kind: Literal["prospective", "paper", "backtest"] = "prospective", risk_pct: float = Query(1.0, gt=0, le=10),
                session: Session = Depends(get_session)):
    if kind == "paper":
        return {"kind": kind, "available": False, "note": KIND_NOTES[kind]}
    if kind == "backtest":
        runs = session.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(50)).all()
        return {"kind": kind, "note": KIND_NOTES[kind], "runs": [_run_summary(r) for r in runs]}
    rows = session.scalars(select(Signal).where(Signal.side.in_(["LONG", "SHORT"]), Signal.outcome.is_not(None))
                           .order_by(Signal.created_at)).all()
    open_count = session.query(Signal).filter(Signal.side.in_(["LONG", "SHORT"]), Signal.outcome.is_(None)).count()
    trades = [{"side": r.side, "symbol": r.symbol, "regime": r.payload.get("regime"), "exit": r.outcome.get("exit"),
               "net_r": r.outcome["net_r"], "exit_time": (r.created_at or datetime.min).isoformat()} for r in rows]
    return {"kind": kind, "note": KIND_NOTES[kind], "closed_signals": len(trades), "open_or_unfilled": open_count,
            "metrics": metrics(trades, risk_pct),
            "claim_policy": "No accuracy rate is claimed. These are measured results of tracked signals only."}


def _run_summary(r: BacktestRun):
    res = r.result
    m = res["full_period"]["metrics"]
    return {"id": r.id, "created_at": r.created_at.isoformat(), "symbol": r.symbol, "market": r.market, "timeframe": r.timeframe,
            "strategy": f"{r.strategy} v{r.strategy_version}", "data_from": res["data_from"], "data_to": res["data_to"],
            "trades": m["trades"], "win_rate": m["win_rate"], "profit_factor": m["profit_factor"], "expectancy_r": m["expectancy_r"],
            "net_pnl_pct": m["net_pnl_pct"], "max_drawdown_pct": m["max_drawdown_pct"],
            "oos_trades": res["splits"]["out_of_sample"]["metrics"]["trades"],
            "oos_expectancy_r": res["splits"]["out_of_sample"]["metrics"]["expectancy_r"],
            "walk_forward_trades": res["walk_forward"]["out_of_sample_metrics"]["trades"],
            "walk_forward_expectancy_r": res["walk_forward"]["out_of_sample_metrics"]["expectancy_r"],
            "warnings": m["warnings"]}


@router.get("/backtests", summary="Stored backtest runs (summaries)")
def backtests(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    runs = session.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)).all()
    return {"runs": [_run_summary(r) for r in runs], "note": KIND_NOTES["backtest"]}


@router.get("/backtests/{run_id}", summary="One backtest with splits, walk-forward folds, trades and equity curve")
def backtest(run_id: str, session: Session = Depends(get_session)):
    r = session.get(BacktestRun, run_id)
    if r is None:
        raise HTTPException(404, "Backtest not found")
    return {"id": r.id, "created_at": r.created_at.isoformat(), **r.result}
