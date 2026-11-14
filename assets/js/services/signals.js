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

  const backend = () => cfg().backendBaseUrl && cfg().backendBaseUrl.replace(/\/$/, "");
  const fromApi = (x) => ({
    id: x.id, symbol: x.symbol.replace(/USDT$/, "/USDT"), market: x.market === "futures" ? "Futures" : "Spot",
    direction: x.side, strategy: x.strategy.replace(/_/g, " "), strategyId: `${x.strategy} v${x.strategy_version}`,
    timeframe: x.timeframe, createdAt: Date.parse(x.generated_at), source: "live", dataSource: x.data_source,
    dataAsOf: x.data_as_of ? Date.parse(x.data_as_of) : null,
    entry: x.entry_low != null ? [x.entry_low, x.entry_high] : null, stop: x.stop ?? null, targets: x.targets || [],
    invalidation: x.invalidation || (x.reasons || []).join("; "), score: x.score ?? 0, lifecycle: x.lifecycle,
    supporting: (x.supporting || []).map((e) => `${e.factor}: ${e.detail}`), conflicting: (x.conflicting || []).map((e) => `${e.factor}: ${e.detail}`),
    explanation: x.explanation, rrNet: x.rr_net, assumptions: x.assumptions
  });

  TA.Signals = {
    isConfigured: () => Boolean(cfg().signalsBaseUrl || backend()),
    LIFECYCLE: ["active", "triggered", "target_reached", "stopped", "expired", "invalidated"],

    async getRecent({ demo } = {}) {
      if (demo) { await wait(600); return { status: "ok", source: "demo", data: structuredClone(TA.DEMO.signals) }; }
      if (backend()) {
        try {
          const res = await fetch(`${backend()}/api/signals?limit=50`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = (await res.json()).signals.map(fromApi);
          return { status: data.length ? "ok" : "empty", source: "live", data };
        } catch (e) { return { status: "error", source: "live", data: null, error: e.message }; }
      }
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
