"""Position sizing from account risk and stop distance. Pure function; JS twin in assets/js/analysis/risk.js.

Per-unit loss at the stop includes estimated costs on both legs:
    per_unit_loss = |entry − stop| + entry·(fee + slippage) + stop·(fee + slippage)
    qty_raw       = (balance · risk%) / per_unit_loss, then rounded DOWN to the exchange step size
Futures (USDT-M, isolated margin, one position) — APPROXIMATE liquidation price, ignoring fees and funding:
    long:  entry · (1 − 1/leverage + mmr)      short: entry · (1 + 1/leverage − mmr)
mmr = maintenance-margin rate (from the exchange's symbol info when available, else a default).
Leverage does not change the amount at risk to the stop; it changes the margin used and how close liquidation is.
"""
from __future__ import annotations

import math
from decimal import Decimal

DEFAULT_MMR = 0.005


def _decimals(step: float) -> int:
    return max(0, -Decimal(repr(step)).normalize().as_tuple().exponent)


def round_down(x: float, step: float | None) -> float:
    if not step:
        return x
    d = _decimals(step)
    return round(math.floor(x / step + 1e-9) * step, d)


def round_to(x: float, step: float | None) -> float:
    if not step:
        return x
    return round(round(x / step) * step, _decimals(step))


def size_position(balance: float, risk_pct: float, entry: float, stop: float, side: str, market: str = "spot",
                  leverage: float = 1.0, fee_rate: float = 0.001, slippage: float = 0.0005, specs: dict | None = None,
                  funding_rate: float | None = None, hold_hours: float = 0.0) -> dict:
    specs = specs or {}
    errors, warnings = [], []
    side = side.upper()
    if balance <= 0:
        errors.append("Account balance must be above 0.")
    if not (0 < risk_pct <= 100):
        errors.append("Risk per trade must be between 0 and 100%.")
    if entry <= 0 or stop <= 0:
        errors.append("Entry and stop must be above 0.")
    if side not in ("LONG", "SHORT"):
        errors.append("Side must be LONG or SHORT.")
    elif entry > 0 and stop > 0 and (stop >= entry if side == "LONG" else stop <= entry):
        errors.append("For a long the stop must be below entry; for a short, above entry.")
    if market == "spot" and leverage != 1:
        errors.append("Spot positions use no leverage (set leverage to 1).")
    if not (1 <= leverage <= 125):
        errors.append("Leverage must be between 1 and 125.")
    if errors:
        return {"valid": False, "errors": errors, "warnings": []}

    tick, step = specs.get("tick_size"), specs.get("step_size")
    min_qty, min_notional = specs.get("min_qty") or 0.0, specs.get("min_notional") or 0.0
    cost = fee_rate + slippage
    risk_amount = balance * risk_pct / 100
    per_unit_loss = abs(entry - stop) + entry * cost + stop * cost
    qty_raw = risk_amount / per_unit_loss
    qty = round_down(qty_raw, step)
    notional = qty * entry
    margin = notional / leverage
    actual_risk = qty * per_unit_loss
    fees_at_stop = qty * (entry + stop) * fee_rate

    if qty <= 0 or qty < min_qty:
        warnings.append(f"Position is below the exchange minimum quantity ({min_qty:g}). This trade can't be sized at this risk level.")
    if min_notional and notional < min_notional:
        warnings.append(f"Order value {notional:.2f} is below the exchange minimum ({min_notional:g}).")
    if margin > balance:
        warnings.append("Margin needed is larger than the balance at this leverage. Reduce size or raise leverage carefully.")
    if risk_pct > 2:
        warnings.append("Risking more than 1–2% per trade is above what many traders consider prudent.")

    liq, liq_before_stop, mmr = None, False, None
    if market == "futures":
        mmr = specs.get("mmr") or DEFAULT_MMR
        liq = entry * (1 - 1 / leverage + mmr) if side == "LONG" else entry * (1 + 1 / leverage - mmr)
        liq = max(liq, 0.0)
        liq_before_stop = liq >= stop if side == "LONG" else liq <= stop
        if liq_before_stop:
            warnings.append("Estimated liquidation price is reached BEFORE the stop. Lower the leverage.")
        if leverage >= 10:
            warnings.append("High leverage magnifies losses and brings liquidation closer.")

    funding_cost = None
    if market == "futures" and funding_rate is not None and hold_hours > 0:
        periods = hold_hours / 8
        paid = notional * funding_rate * periods * (1 if side == "LONG" else -1)   # >0 = you pay
        funding_cost = paid
        if paid > 0.25 * risk_amount:
            warnings.append("Estimated funding over the holding time is more than 25% of the amount at risk.")

    return {
        "valid": True, "errors": [], "warnings": warnings, "side": side, "market": market,
        "risk_amount": risk_amount, "per_unit_loss": per_unit_loss, "qty_raw": qty_raw, "qty": qty,
        "notional": notional, "margin": margin, "leverage": leverage, "actual_risk": actual_risk,
        "actual_risk_pct": actual_risk / balance * 100, "fees_at_stop": fees_at_stop,
        "entry_rounded": round_to(entry, tick), "stop_rounded": round_to(stop, tick),
        "liquidation_price": liq, "liquidation_before_stop": liq_before_stop, "mmr": mmr,
        "funding_cost": funding_cost, "r_multiple_value": actual_risk,
        "assumptions": {"fee_rate_per_side": fee_rate, "slippage_per_side": slippage, "mmr": mmr,
                        "note": "Estimates. Liquidation uses a simplified isolated-margin formula; exchanges use tiered "
                                "maintenance margin and fees, so the real level can differ. Leverage magnifies losses."},
    }
