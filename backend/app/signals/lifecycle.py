"""Signal lifecycle tracking — deterministic and conservative. Pure function of the signal and candles.

Candles used: those that OPEN at or after the signal's `data_as_of` and have CLOSED by `now`.
Only candle OHLC is known, not the order of prices inside a candle, so ambiguities resolve against the trade:

Before entry (state "active"):
  * entry is "triggered" when price trades into the zone (long: low ≤ entry_high; short: high ≥ entry_low).
    Fill price = entry_high for longs / entry_low for shorts (the worse edge), or the candle open if it
    gapped inside the zone.
  * "invalidated" if a candle CLOSES beyond the stop before entry.
  * "expired" if no entry by `expires_at`.
After entry ("triggered", then "target_reached" once TP1 is hit):
  * on the entry candle itself only the stop is checked (targets are not credited on that candle);
  * stop hit when low ≤ stop (long) / high ≥ stop (short);
  * if the stop and a new target are both touched in the same candle → the STOP is assumed first and the
    event is flagged `ambiguous_same_candle` (finer-grained data would be needed to know);
  * TP3 closes the trade ("target_reached", terminal); stop after TP1 ends as "stopped";
  * time exit at the close of the candle `max_hold_bars` after entry → "expired".
Simulated outcome (for record-keeping, not a performance claim): one third exits at each of TP1/TP2/TP3,
the remainder at the stop or time-exit price; R = move / (fill − stop); net R subtracts entry+exit
fee and slippage from the signal's assumptions. Funding is not included.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..providers.base import INTERVAL_MS

TERMINAL = {"stopped", "expired", "invalidated", "closed"}


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _ms(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp() * 1000


def track(sig: dict, series: dict, now: datetime, max_hold_bars: int | None = None) -> dict:
    side = sig["side"]
    if side not in ("LONG", "SHORT"):
        return {"lifecycle": sig.get("lifecycle", "no_trade"), "terminal": True, "events": [], "outcome": None}
    long_ = side == "LONG"
    step = INTERVAL_MS[sig["timeframe"]]
    start, expires = _ms(sig["data_as_of"]), _ms(sig["expires_at"])
    max_hold = max_hold_bars or 4 * int(sig.get("config", {}).get("expiry_bars", 12))
    lo, hi, stop, tps = sig["entry_low"], sig["entry_high"], sig["stop"], list(sig["targets"])
    now_ms = now.timestamp() * 1000
    idx = [i for i, t in enumerate(series["t"]) if t >= start and t + step <= now_ms]

    events, state, fill, entry_i, hit = [], "active", None, None, 0
    exit_price, exit_kind = None, None

    def ev(kind, i, price, **detail):
        events.append({"seq": len(events) + 1, "type": kind, "at": _iso(series["t"][i] + step), "price": price, "detail": detail})

    for n, i in enumerate(idx):
        o, h, l, c, t = (series[k][i] for k in ("o", "h", "l", "c", "t"))
        if state == "active":
            touched = l <= hi if long_ else h >= lo
            if touched:
                fill = (min(o, hi) if long_ and lo <= o <= hi else hi) if long_ else (max(o, lo) if lo <= o <= hi else lo)
                state, entry_i = "triggered", n
                ev("triggered", i, fill, rule="zone touched; fill at the worse zone edge unless the candle opened inside it")
                if (l <= stop) if long_ else (h >= stop):
                    state, exit_price, exit_kind = "stopped", stop, "stop"
                    ev("stopped", i, stop, ambiguous_same_candle=True, rule="stop touched on the entry candle")
                    break
                continue
            if (c < stop) if long_ else (c > stop):
                state = "invalidated"; ev("invalidated", i, c, rule="closed beyond the stop before entry"); break
            if t >= expires:
                state = "expired"; ev("expired", i, c, rule="no entry before expiry"); break
            continue
        # after entry
        stop_hit = (l <= stop) if long_ else (h >= stop)
        reach = sum(1 for tp in tps if (h >= tp if long_ else l <= tp))
        new_tp = reach > hit
        if stop_hit:
            state, exit_price, exit_kind = "stopped", stop, "stop"
            ev("stopped", i, stop, ambiguous_same_candle=bool(new_tp), after_targets=hit,
               rule="stop assumed first when stop and target touch in the same candle" if new_tp else "stop touched")
            break
        while hit < reach:
            hit += 1
            ev(f"tp{hit}_hit", i, tps[hit - 1])
        if hit == 3:
            state, exit_kind = "closed", "tp3"; break
        if hit >= 1:
            state = "target_reached"
        if n - entry_i >= max_hold:
            state, exit_price, exit_kind = "expired", c, "time"
            ev("expired", i, c, rule=f"time exit after {max_hold} candles in the trade", after_targets=hit); break

    outcome = None
    if state in TERMINAL and fill is not None:
        risk = abs(fill - stop)
        parts = [(tps[k] - fill if long_ else fill - tps[k]) / risk for k in range(min(hit, 3))]
        rest = 3 - len(parts)
        if rest:
            px = exit_price if exit_price is not None else fill
            parts += [((px - fill) if long_ else (fill - px)) / risk] * rest
        gross = sum(parts) / 3
        a = sig.get("assumptions", {})
        cost_r = fill * 2 * (a.get("fee_rate_per_side", 0) + a.get("slippage_per_side", 0)) / risk
        outcome = {"fill": fill, "exit": exit_kind, "targets_hit": hit, "gross_r": round(gross, 6), "net_r": round(gross - cost_r, 6),
                   "model": "thirds at TP1/TP2/TP3, remainder at stop or time exit; fees+slippage from the signal; funding excluded",
                   "simulated": True}
    lifecycle = {"closed": "target_reached"}.get(state, state)
    return {"lifecycle": lifecycle, "terminal": state in TERMINAL, "events": events, "outcome": outcome}
