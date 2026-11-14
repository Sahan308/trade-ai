/*
 * Position sizing — JavaScript twin of backend/app/risk/sizing.py (formulas documented there).
 * Parity is checked by backend/tests/test_parity.py.
 */
(function () {
  const root = typeof window !== "undefined" ? window : globalThis;
  const TA = (root.TA = root.TA || {});
  const DEFAULT_MMR = 0.005;
  function decimals(step) {
    const s = String(step);
    if (s.includes("e-")) { const [m, e] = s.split("e-"); return (m.split(".")[1] || "").length + Number(e); }
    return (s.split(".")[1] || "").replace(/0+$/, "").length;
  }
  const roundDown = (x, step) => (step ? Number((Math.floor(x / step + 1e-9) * step).toFixed(decimals(step))) : x);
  const roundTo = (x, step) => (step ? Number((Math.round(x / step) * step).toFixed(decimals(step))) : x);

  function sizePosition({ balance, riskPct, entry, stop, side, market = "spot", leverage = 1, feeRate = 0.001, slippage = 0.0005, specs = null, fundingRate = null, holdHours = 0 }) {
    specs = specs || {};
    const errors = [], warnings = [];
    side = String(side).toUpperCase();
    if (!(balance > 0)) errors.push("Account balance must be above 0.");
    if (!(riskPct > 0 && riskPct <= 100)) errors.push("Risk per trade must be between 0 and 100%.");
    if (!(entry > 0) || !(stop > 0)) errors.push("Entry and stop must be above 0.");
    if (side !== "LONG" && side !== "SHORT") errors.push("Side must be LONG or SHORT.");
    else if (entry > 0 && stop > 0 && (side === "LONG" ? stop >= entry : stop <= entry)) errors.push("For a long the stop must be below entry; for a short, above entry.");
    if (market === "spot" && leverage !== 1) errors.push("Spot positions use no leverage (set leverage to 1).");
    if (!(leverage >= 1 && leverage <= 125)) errors.push("Leverage must be between 1 and 125.");
    if (errors.length) return { valid: false, errors, warnings: [] };

    const tick = specs.tick_size, step = specs.step_size, minQty = specs.min_qty || 0, minNotional = specs.min_notional || 0;
    const cost = feeRate + slippage, riskAmount = (balance * riskPct) / 100;
    const perUnitLoss = Math.abs(entry - stop) + entry * cost + stop * cost;
    const qtyRaw = riskAmount / perUnitLoss, qty = roundDown(qtyRaw, step);
    const notional = qty * entry, margin = notional / leverage, actualRisk = qty * perUnitLoss, feesAtStop = qty * (entry + stop) * feeRate;
    if (qty <= 0 || qty < minQty) warnings.push(`Position is below the exchange minimum quantity (${minQty}). This trade can't be sized at this risk level.`);
    if (minNotional && notional < minNotional) warnings.push(`Order value ${notional.toFixed(2)} is below the exchange minimum (${minNotional}).`);
    if (margin > balance) warnings.push("Margin needed is larger than the balance at this leverage. Reduce size or raise leverage carefully.");
    if (riskPct > 2) warnings.push("Risking more than 1–2% per trade is above what many traders consider prudent.");

    let liq = null, liqBeforeStop = false, mmr = null;
    if (market === "futures") {
      mmr = specs.mmr || DEFAULT_MMR;
      liq = Math.max(side === "LONG" ? entry * (1 - 1 / leverage + mmr) : entry * (1 + 1 / leverage - mmr), 0);
      liqBeforeStop = side === "LONG" ? liq >= stop : liq <= stop;
      if (liqBeforeStop) warnings.push("Estimated liquidation price is reached BEFORE the stop. Lower the leverage.");
      if (leverage >= 10) warnings.push("High leverage magnifies losses and brings liquidation closer.");
    }
    let fundingCost = null;
    if (market === "futures" && fundingRate !== null && fundingRate !== undefined && holdHours > 0) {
      const paid = notional * fundingRate * (holdHours / 8) * (side === "LONG" ? 1 : -1);
      fundingCost = paid;
      if (paid > 0.25 * riskAmount) warnings.push("Estimated funding over the holding time is more than 25% of the amount at risk.");
    }
    return {
      valid: true, errors: [], warnings, side, market, risk_amount: riskAmount, per_unit_loss: perUnitLoss, qty_raw: qtyRaw, qty,
      notional, margin, leverage, actual_risk: actualRisk, actual_risk_pct: (actualRisk / balance) * 100, fees_at_stop: feesAtStop,
      entry_rounded: roundTo(entry, tick), stop_rounded: roundTo(stop, tick), liquidation_price: liq, liquidation_before_stop: liqBeforeStop,
      mmr, funding_cost: fundingCost, r_multiple_value: actualRisk,
      assumptions: { fee_rate_per_side: feeRate, slippage_per_side: slippage, mmr, note: "Estimates. Liquidation uses a simplified isolated-margin formula; exchanges use tiered maintenance margin and fees, so the real level can differ. Leverage magnifies losses." }
    };
  }
  TA.Risk = { sizePosition, roundDown, roundTo, decimals };
})();
