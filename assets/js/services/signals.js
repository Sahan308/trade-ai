/*
 * Signals service. No signal engine lives in the frontend — signals must come from an approved backend.
 * Expected backend contract:
 *   GET {signalsBaseUrl}/recent  -> [Signal]
 *   GET {signalsBaseUrl}/usage   -> { used, limit }
 * Signal: { id, symbol, market, direction: "LONG"|"SHORT"|"NO TRADE", strategy, timeframe, createdAt,
 *           dataSource, entry:[lo,hi]|null, stop, targets[], invalidation, score (heuristic 0–100),
 *           lifecycle: "active"|"triggered"|"target_reached"|"stopped"|"expired"|"invalidated",
 *           supporting[], conflicting[] }
 */
(function () {
  const TA = (window.TA = window.TA || {});
  const cfg = () => window.TRADE_AI_CONFIG.api;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  TA.Signals = {
    isConfigured: () => Boolean(cfg().signalsBaseUrl),
    LIFECYCLE: ["active", "triggered", "target_reached", "stopped", "expired", "invalidated"],

    async getRecent({ demo } = {}) {
      if (demo) { await wait(600); return { status: "ok", source: "demo", data: structuredClone(TA.DEMO.signals) }; }
      if (!this.isConfigured()) return { status: "disconnected", source: "live", data: null };
      try {
        const res = await fetch(`${cfg().signalsBaseUrl}/recent`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        return { status: data.length ? "ok" : "empty", source: "live", data };
      } catch (e) { return { status: "error", source: "live", data: null, error: e.message }; }
    },

    async getUsage({ demo } = {}) {
      const limit = window.TRADE_AI_CONFIG.pricing.trialSignals;
      if (demo) return { status: "ok", source: "demo", data: { used: TA.DEMO.trialUsed, limit } };
      if (!this.isConfigured()) return { status: "disconnected", source: "live", data: { used: null, limit } };
      try {
        const res = await fetch(`${cfg().signalsBaseUrl}/usage`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return { status: "ok", source: "live", data: await res.json() };
      } catch (e) { return { status: "error", source: "live", data: { used: null, limit }, error: e.message }; }
    }
  };
})();
