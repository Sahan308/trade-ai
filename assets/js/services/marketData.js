/*
 * Market data service — the only thing UI code calls for market data.
 * Source priority (never silently mixed):
 *   1. demo        — isolated fixtures, only when the user switches on "Sample data"
 *   2. backend     — TRADE-AI API, when api.backendBaseUrl is set
 *   3. provider    — public exchange adapter in the browser (api.publicProvider, e.g. "binance")
 *   4. none        — disconnected state; nothing is invented
 * Result shape: { status: "ok"|"empty"|"disconnected"|"error", source, data, fetchedAt, error?, meta? }
 */
(function () {
  const TA = (window.TA = window.TA || {});
  const cfg = () => window.TRADE_AI_CONFIG;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const provider = () => TA.Providers && TA.Providers[cfg().api.publicProvider];

  function mode(demo) {
    if (demo) return "demo";
    if (cfg().api.backendBaseUrl) return "backend";
    if (provider()) return "provider";
    return "none";
  }
  const fail = (e) => ({ status: "error", data: null, error: e.message || String(e), retryAfter: e.retryAfter });

  async function backendGet(path, params) {
    const url = new URL(cfg().api.backendBaseUrl.replace(/\/$/, "") + path);
    Object.entries(params || {}).forEach(([k, v]) => url.searchParams.set(k, v));
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(body?.error?.message || `API error (HTTP ${res.status})`);
    return body;
  }
  const apiSym = (s) => s.replace("/", "");

  TA.MarketData = {
    mode,
    isConfigured: () => mode(false) !== "none",
    describeSource(demo) {
      const m = mode(demo);
      return { demo: "Sample fixture", backend: "TRADE-AI API", provider: "Binance public data", none: "Not connected" }[m];
    },
    watchlistSymbols: () => cfg().watchlist,

    async getWatchlist({ demo } = {}) {
      const m = mode(demo);
      if (m === "demo") { await wait(400); return { status: "ok", source: "demo", data: structuredClone(TA.DEMO.watchlist), fetchedAt: Date.now() }; }
      if (m === "none") return { status: "disconnected", data: null };
      try {
        let data;
        if (m === "provider") data = await provider().tickers(cfg().watchlist);
        else data = await Promise.all(cfg().watchlist.map((w) => backendGet(`/api/markets/${apiSym(w.symbol)}/ticker`, { market: w.market.toLowerCase() })
          .then((t) => ({ symbol: w.symbol, market: w.market, last: t.last_price, change24h: t.change_24h_pct, volume: t.quote_volume_24h, dataTime: Date.parse(t.data_time), source: t.source }))));
        return { status: data.length ? "ok" : "empty", source: m, data, fetchedAt: Date.now() };
      } catch (e) { return { ...fail(e), source: m }; }
    },

    async getCandles(symbol, market, tf, { demo, limit = 120 } = {}) {
      const m = mode(demo);
      if (m === "demo") {
        await wait(300);
        const seed = { "15m": 3, "1H": 7, "4H": 11, "1D": 19 }[tf] || 7;
        return { status: "ok", source: "demo", sourceName: "Sample fixture", data: TA.DEMO.candles(72, 100, seed), fetchedAt: Date.now() };
      }
      if (m === "none") return { status: "disconnected", data: null };
      try {
        if (m === "provider") {
          const r = await provider().candles(market, symbol, tf, limit);
          return { status: r.candles.length ? "ok" : "empty", source: m, sourceName: r.source, data: r.candles, fetchedAt: r.fetchedAt, meta: { gaps: r.gaps, dropped: r.dropped } };
        }
        const r = await backendGet(`/api/markets/${apiSym(symbol)}/candles`, { market: market.toLowerCase(), interval: tf, limit });
        const data = r.candles.map((c) => ({ t: Date.parse(c.open_time), o: c.open, h: c.high, l: c.low, c: c.close, v: c.volume }));
        return { status: data.length ? "ok" : "empty", source: m, sourceName: r.source, data, fetchedAt: Date.parse(r.fetched_at), meta: { gaps: r.gaps } };
      } catch (e) { return { ...fail(e), source: m }; }
    },

    /** Live updates. Only the browser provider streams; returns null when streaming isn't available. */
    streamCandles(symbol, market, tf, onCandle, onStatus, { demo } = {}) {
      if (mode(demo) !== "provider") return null;
      try { return provider().streamKlines(market, symbol, tf, onCandle, onStatus); } catch { return null; }
    },

    async getPremium(symbol, { demo } = {}) {
      const m = mode(demo);
      if (m === "demo" || m === "none") return { status: m === "none" ? "disconnected" : "empty", data: null };
      try {
        if (m === "provider") return { status: "ok", source: m, data: await provider().premium(symbol), fetchedAt: Date.now() };
        const r = await backendGet(`/api/futures/${apiSym(symbol)}/funding`);
        return { status: "ok", source: m, fetchedAt: Date.now(), data: { mark: r.mark_price, index: r.index_price, fundingRate: r.funding_rate, nextFundingTime: Date.parse(r.next_funding_time), dataTime: Date.parse(r.data_time), source: r.source } };
      } catch (e) { return { ...fail(e), source: m }; }
    },

    streamPremium(symbol, onData, onStatus, { demo } = {}) {
      if (mode(demo) !== "provider") return null;
      try { return provider().streamPremium(symbol, onData, onStatus); } catch { return null; }
    }
  };
})();
