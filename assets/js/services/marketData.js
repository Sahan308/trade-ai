/*
 * Market data service. UI components never fetch directly — they call this.
 * Result shape: { status: "ok" | "disconnected" | "error" | "empty", source: "live" | "demo", data, fetchedAt, error? }
 * Expected backend contract (to be implemented server-side):
 *   GET {marketDataBaseUrl}/watchlist            -> [{ symbol, market, last, change24h, volume }]
 *   GET {marketDataBaseUrl}/candles?symbol=&tf=  -> [{ t, o, h, l, c, v }]
 */
(function () {
  const TA = (window.TA = window.TA || {});
  const cfg = () => window.TRADE_AI_CONFIG.api;

  async function getJSON(url) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), cfg().requestTimeoutMs);
    try {
      const res = await fetch(url, { signal: ctrl.signal, headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } finally { clearTimeout(timer); }
  }

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  TA.MarketData = {
    isConfigured: () => Boolean(cfg().marketDataBaseUrl),

    async getWatchlist({ demo } = {}) {
      if (demo) { await wait(500); return { status: "ok", source: "demo", data: structuredClone(TA.DEMO.watchlist), fetchedAt: Date.now() }; }
      if (!this.isConfigured()) return { status: "disconnected", source: "live", data: null };
      try {
        const data = await getJSON(`${cfg().marketDataBaseUrl}/watchlist`);
        return { status: data.length ? "ok" : "empty", source: "live", data, fetchedAt: Date.now() };
      } catch (e) { return { status: "error", source: "live", data: null, error: e.message }; }
    },

    async getCandles(symbol, tf, { demo } = {}) {
      if (demo) {
        await wait(350);
        const seed = { "15m": 3, "1H": 7, "4H": 11, "1D": 19 }[tf] || 7;
        return { status: "ok", source: "demo", data: TA.DEMO.candles(72, 100, seed), fetchedAt: Date.now() };
      }
      if (!this.isConfigured()) return { status: "disconnected", source: "live", data: null };
      try {
        const data = await getJSON(`${cfg().marketDataBaseUrl}/candles?symbol=${encodeURIComponent(symbol)}&tf=${tf}`);
        return { status: data.length ? "ok" : "empty", source: "live", data, fetchedAt: Date.now() };
      } catch (e) { return { status: "error", source: "live", data: null, error: e.message }; }
    }
  };
})();
