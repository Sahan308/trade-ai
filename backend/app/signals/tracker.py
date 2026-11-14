"""Apply lifecycle tracking to stored signals: append new events, update lifecycle/outcome, raise alerts."""
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Alert, Signal, SignalEvent
from ..providers.base import INTERVAL_MS, MarketType, ProviderError
from .lifecycle import track

log = logging.getLogger("tradeai.tracker")
OPEN_STATES = ("active", "triggered", "target_reached")
LABEL = {"triggered": "Entry triggered", "tp1_hit": "Target 1 reached", "tp2_hit": "Target 2 reached", "tp3_hit": "Target 3 reached",
         "stopped": "Stopped out", "expired": "Expired", "invalidated": "Invalidated"}


def fmt(x):
    return f"{x:.6g}" if isinstance(x, (int, float)) else str(x)


def alert_for_new_signal(session: Session, row: Signal) -> None:
    p = row.payload
    session.add(Alert(signal_id=row.id, kind="new_signal", symbol=row.symbol,
                      title=f"New {row.side} setup · {row.symbol} {row.timeframe}",
                      message=f"Entry {fmt(p['entry_low'])}–{fmt(p['entry_high'])}, stop {fmt(p['stop'])}, TP1 {fmt(p['targets'][0])}. "
                              "Analysis only — no order has been placed."))


def apply(session: Session, row: Signal, series: dict, now: datetime) -> list[dict]:
    res = track(row.payload, series, now)
    have = session.scalar(select(func.coalesce(func.max(SignalEvent.seq), 0)).where(SignalEvent.signal_id == row.id))
    new = [e for e in res["events"] if e["seq"] > have]
    for e in new:
        session.add(SignalEvent(signal_id=row.id, seq=e["seq"], type=e["type"], at=datetime.fromisoformat(e["at"]),
                                price=e["price"], detail=e["detail"]))
        extra = " (stop and target touched in the same candle — stop assumed first)" if e["detail"].get("ambiguous_same_candle") else ""
        session.add(Alert(signal_id=row.id, kind=e["type"], symbol=row.symbol,
                          title=f"{LABEL.get(e['type'], e['type'])} · {row.side} {row.symbol} {row.timeframe}",
                          message=f"At {fmt(e['price'])} on the candle closing {e['at']}{extra}."))
    if res["lifecycle"] != row.lifecycle:
        row.lifecycle = res["lifecycle"]
    if res["outcome"] and row.outcome != res["outcome"]:
        row.outcome = res["outcome"]
    session.commit()
    return new


def track_open(session: Session, provider, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    rows = session.scalars(select(Signal).where(Signal.side.in_(["LONG", "SHORT"]), Signal.lifecycle.in_(OPEN_STATES))).all()
    total = 0
    for row in rows:
        step = INTERVAL_MS[row.timeframe]
        since = row.data_as_of.replace(tzinfo=row.data_as_of.tzinfo or timezone.utc) if row.data_as_of else now
        bars = int((now - since).total_seconds() * 1000 // step) + 2
        try:
            s = provider.candles(MarketType(row.market), row.symbol, row.timeframe, min(1000, max(2, bars)))
        except ProviderError as exc:
            log.warning("tracking %s skipped: %s", row.symbol, exc.message)
            continue
        cs = s.candles
        series = {"t": [x.open_time.timestamp() * 1000 for x in cs], "o": [x.open for x in cs], "h": [x.high for x in cs],
                  "l": [x.low for x in cs], "c": [x.close for x in cs], "v": [x.volume for x in cs]}
        total += len(apply(session, row, series, now))
    return total
