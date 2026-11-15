/* TRADE-AI Market Risk Monitor model: a direct port of research round-4 candidate E3
   (research/run_r4.py, research/PROTOCOL_R4.md). Trend ensemble of 9 Donchian lookbacks, 25% volatility targeting,
   1/20 cap per coin, top-20 liquidity universe, BTC regime filter. Pure functions; parity-tested against the Python. */
(function () {
  const root = typeof window !== "undefined" ? window : globalThis;
  const TA = (root.TA = root.TA || {});
  const LOOKBACKS = [5, 10, 20, 30, 60, 90, 150, 250, 360];
  const P = { topN: 20, minHist: 365, volTarget: 0.25, volWindow: 90 };
  const UNIVERSE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "TRXUSDT", "XLMUSDT",
    "ETCUSDT", "BCHUSDT", "EOSUSDT", "ATOMUSDT", "XTZUSDT", "NEOUSDT", "VETUSDT", "ZECUSDT", "DASHUSDT", "QTUMUSDT",
    "SOLUSDT", "DOTUSDT", "AVAXUSDT", "UNIUSDT", "FILUSDT"];

  /** Per-candle ensemble score (fraction of the 9 sub-signals ON) and per-lookback state at the last candle. */
  function ensemble(c) {
    const n = c.length, score = new Array(n).fill(0), last = [];
    for (const L of LOOKBACKS) {
      let on = false, stop = null;
      for (let i = L; i < n; i++) {
        let hi = -Infinity, lo = Infinity;
        for (let k = i - L; k < i; k++) { if (c[k] > hi) hi = c[k]; if (c[k] < lo) lo = c[k]; }
        const mid = (hi + lo) / 2;
        if (!on && c[i] > hi) { on = true; stop = mid; }
        else if (on) { stop = Math.max(stop, mid); if (c[i] < stop) { on = false; stop = null; } }
        if (on) score[i] += 1 / LOOKBACKS.length;
      }
      last.push({ lookback: L, on, stop });
    }
    return { score, last };
  }

  function annVol(c, i, n = P.volWindow) {
    if (i < n) return null;
    const r = [];
    for (let k = i - n + 1; k <= i; k++) r.push(Math.log(c[k] / c[k - 1]));
    const m = r.reduce((a, b) => a + b, 0) / n;
    return Math.sqrt(r.reduce((a, x) => a + (x - m) ** 2, 0) / (n - 1)) * Math.sqrt(365);
  }

  /** series: { SYMBOL: {t:[], c:[], v:[]} } of CLOSED daily candles. Returns the model state at the latest common day. */
  function evaluate(series) {
    const rows = [];
    for (const [sym, d] of Object.entries(series)) {
      const i = d.c.length - 1;
      if (i + 1 < P.minHist) { rows.push({ sym, eligible: false, reason: "under 1 year of history" }); continue; }
      const qv = [];
      for (let j = Math.max(0, i - 29); j <= i; j++) qv.push(d.c[j] * d.v[j]);
      qv.sort((a, b) => a - b);
      const ens = ensemble(d.c), vol = annVol(d.c, i);
      rows.push({ sym, liq: qv[Math.floor(qv.length / 2)], score: ens.score[i], subs: ens.last, vol, close: d.c[i], t: d.t[i] });
    }
    const ranked = rows.filter((r) => r.liq != null).sort((a, b) => b.liq - a.liq);
    ranked.forEach((r, k) => { r.eligible = k < P.topN; if (!r.eligible) r.reason = "outside top-20 liquidity"; });
    for (const r of ranked) {
      if (!r.eligible || r.score <= 0 || !r.vol) { r.weight = 0; continue; }
      r.weight = Math.min(r.score * Math.min(1, P.volTarget / r.vol), 1 / P.topN);
    }
    const btc = rows.find((r) => r.sym === "BTCUSDT");
    const riskOff = !btc || btc.score == null || btc.score < 0.5;
    if (riskOff) ranked.forEach((r) => (r.weight = (r.weight || 0) / 2));
    let total = ranked.reduce((a, r) => a + (r.weight || 0), 0);
    if (total > 1) { ranked.forEach((r) => (r.weight /= total)); total = 1; }
    return { asOf: btc ? btc.t : null, btcScore: btc ? btc.score : null, regime: riskOff ? "risk-off" : "risk-on",
      exposure: total, rows: [...ranked, ...rows.filter((r) => r.liq == null)] };
  }

  TA.Regime = { evaluate, ensemble, annVol, LOOKBACKS, UNIVERSE, params: P };
  if (typeof module !== "undefined") module.exports = TA.Regime;
})();
