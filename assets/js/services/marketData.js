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
  const fallback = () => TA.Providers && TA.Providers[cfg().api.futuresFallbackProvider];

  // Futures region fallback: if the primary futures endpoint is region-blocked or unreachable,
  // switch futures calls to the fallback provider for this browser session (and label it).
  const fb = {
    get on() { try { return sessionStorage.getItem("ta-fut-fallback") === "1"; } catch { return false; } },
    set on(v) { try { sessionStorage.setItem("ta-fut-fallback", v ? "1" : "0"); } catch {} }
  };
  const isFutures = (m) => String(m).toLowerCase() === "futures";
  const futProvider = () => (fb.on && fallback()) || provider();
  async function withFallback(market, fn) {
    if (!isFutures(market)) return fn(provider());
    try { return await fn(futProvider()); }
    catch (e) {
      const blocked = e && (e.kind === "region" || e.kind === "network");
      if (blocked && !fb.on && fallback()) { fb.on = true; return fn(fallback()); }
      throw e;
    }
  }

  function mode(demo) {
    if (demo) return "demo";
    if (cfg().api.backendBaseUrl && cfg().api.marketDataSource === "backend") return "backend";
    if (provider()) return "provider";
    if (cfg().api.backendBaseUrl) return "backend";
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
  const fromApiCandle = (c) => ({ t: Date.parse(c.open_time), o: c.open, h: c.high, l: c.low, c: c.close, v: c.volume });

  /** WebSocket to the TRADE-AI backend with backoff reconnect and a stale timer. */
  function backendStream(path, params, onMessage, onStatus = () => {}) {
    const url = new URL(cfg().api.backendBaseUrl.replace(/\/$/, "") + path);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    const STALE_MS = 45000; let ws, staleT, retryT, attempt = 0, closed = false, opened = false;
    const arm = () => { clearTimeout(staleT); staleT = setTimeout(() => { onStatus("stale"); try { ws.close(); } catch {} }, STALE_MS); };
    const connect = () => {
      if (closed) return;
      onStatus(opened ? "reconnecting" : "connecting", {});
      try { ws = new WebSocket(url); } catch { return schedule(); }
      ws.onopen = () => { attempt = 0; const re = opened; opened = true; onStatus("live", { reconnected: re }); arm(); };
      ws.onmessage = (e) => { arm(); try { onMessage(JSON.parse(e.data)); } catch {} };
      ws.onclose = () => { clearTimeout(staleT); if (!closed) schedule(); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    const schedule = () => { clearTimeout(retryT); const d = Math.min(30000, 1000 * 2 ** attempt++) + Math.random() * 500; onStatus("reconnecting", { inMs: d }); retryT = setTimeout(connect, d); };
    connect();
    return { close() { closed = true; clearTimeout(staleT); clearTimeout(retryT); try { ws && ws.close(); } catch {} onStatus("closed"); } };
  }

  TA.MarketData = {
    mode,
    isConfigured: () => mode(false) !== "none",
    usingFuturesFallback: () => fb.on && !!fallback(),
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
        if (m === "provider") {
          const spot = cfg().watchlist.filter((w) => !isFutures(w.market)), fut = cfg().watchlist.filter((w) => isFutures(w.market));
          const [a, b] = await Promise.all([spot.length ? provider().tickers(spot) : [], fut.length ? withFallback("futures", (p) => p.tickers(fut)) : []]);
          data = [...a, ...b];
        }
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
          const r = await withFallback(market, (p) => p.candles(market, symbol, tf, limit));
          return { status: r.candles.length ? "ok" : "empty", source: m, sourceName: r.source, data: r.candles, fetchedAt: r.fetchedAt, meta: { gaps: r.gaps, dropped: r.dropped } };
        }
        const r = await backendGet(`/api/markets/${apiSym(symbol)}/candles`, { market: market.toLowerCase(), interval: tf, limit });
        const data = r.candles.map((c) => ({ t: Date.parse(c.open_time), o: c.open, h: c.high, l: c.low, c: c.close, v: c.volume }));
        return { status: data.length ? "ok" : "empty", source: m, sourceName: r.source, data, fetchedAt: Date.parse(r.fetched_at), meta: { gaps: r.gaps } };
      } catch (e) { return { ...fail(e), source: m }; }
    },

    /** Live updates. Only the browser provider streams; returns null when streaming isn't available. */
    streamCandles(symbol, market, tf, onCandle, onStatus, { demo } = {}) {
      const m = mode(demo);
      if (m === "backend") return backendStream(`/ws/chart/${apiSym(symbol)}/${tf}`, { market: market.toLowerCase() }, (msg) => {
        if (msg.type === "candle") onCandle(fromApiCandle(msg.candle), msg.closed);
        else if (msg.type === "snapshot") msg.candles.forEach((c) => onCandle(fromApiCandle(c), true));
        else if (msg.type === "status") onStatus(msg.status, { upstream: true });
      }, onStatus);
      if (m !== "provider") return null;
      try { return (isFutures(market) ? futProvider() : provider()).streamKlines(market, symbol, tf, onCandle, onStatus); } catch { return null; }
    },

    async getSpecs(symbol, market) {
      const m = mode(false);
      if (m === "none") return { status: "disconnected", data: null };
      try {
        if (m === "provider") return { status: "ok", data: await withFallback(market, (p) => p.specs(market, symbol)) };
        return { status: "ok", data: await backendGet(`/api/markets/${apiSym(symbol)}/specs`, { market: market.toLowerCase() }) };
      } catch (e) { return fail(e); }
    },

    async getPremium(symbol, { demo } = {}) {
      const m = mode(demo);
      if (m === "demo" || m === "none") return { status: m === "none" ? "disconnected" : "empty", data: null };
      try {
        if (m === "provider") return { status: "ok", source: m, data: await withFallback("futures", (p) => p.premium(symbol)), fetchedAt: Date.now() };
        const r = await backendGet(`/api/futures/${apiSym(symbol)}/funding`);
        return { status: "ok", source: m, fetchedAt: Date.now(), data: { mark: r.mark_price, index: r.index_price, indexLabel: r.index_label, fundingRate: r.funding_rate, nextFundingTime: Date.parse(r.next_funding_time), dataTime: Date.parse(r.data_time), source: r.source } };
      } catch (e) { return { ...fail(e), source: m }; }
    },

    streamPremium(symbol, onData, onStatus, { demo } = {}) {
      const m = mode(demo);
      if (m === "backend") return backendStream(`/ws/market/${apiSym(symbol)}`, {}, (msg) => {
        if (msg.type === "funding") { const r = msg.data; onData({ mark: r.mark_price, index: r.index_price, indexLabel: r.index_label, fundingRate: r.funding_rate, nextFundingTime: Date.parse(r.next_funding_time), dataTime: Date.parse(r.data_time), source: r.source }); }
        else if (msg.type === "status") onStatus(msg.status, { upstream: true });
      }, onStatus);
      if (m !== "provider") return null;
      try { return futProvider().streamPremium(symbol, onData, onStatus); } catch { return null; }
    }
  };
})();
