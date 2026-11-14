/*
 * Hyperliquid public market-data adapter (browser) — FUTURES FALLBACK ONLY.
 * Used when Binance USDT-M Futures is region-blocked or unreachable. No API key, read-only.
 * Hyperliquid perpetuals are USDC-settled and quoted in USD, so prices can differ slightly
 * from Binance USDT-M; every value is labelled with this source.
 *   REST  POST https://api.hyperliquid.xyz/info
 *   WS    wss://api.hyperliquid.xyz/ws   (subscribe: candle, activeAssetCtx)
 * Mark price = markPx. Hyperliquid has no "index price"; its closest equivalent is the oracle price.
 */
(function () {
  const TA = (window.TA = window.TA || {});
  const REST = "https://api.hyperliquid.xyz/info", WS = "wss://api.hyperliquid.xyz/ws";
  const SOURCE = "Hyperliquid perpetuals (fallback)";
  const INTERVALS = { "1m": "1m", "5m": "5m", "15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d" };
  const INTERVAL_MS = { "1m": 60e3, "5m": 300e3, "15m": 900e3, "1H": 3600e3, "4H": 14400e3, "1D": 86400e3 };
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : NaN; };
  const Err = (m, o) => new (TA.ProviderError || Error)(m, o);

  const coin = (symbol) => {
    const c = String(symbol).toUpperCase().replace(/[^A-Z0-9]/g, "").replace(/USDT?$/, "").replace(/USDC$/, "");
    if (!/^[A-Z0-9]{2,12}$/.test(c)) throw Err(`Invalid symbol: ${symbol}`);
    return c;
  };

  async function info(body) {
    const ctrl = new AbortController(), t = setTimeout(() => ctrl.abort(), 8000);
    let res;
    try { res = await fetch(REST, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal }); }
    catch (e) { throw Err(e.name === "AbortError" ? "Fallback provider timed out" : "Fallback provider unreachable"); }
    finally { clearTimeout(t); }
    if (res.status === 429) throw Err("Rate limited by fallback provider", { status: 429, retryAfter: 60 });
    if (!res.ok) throw Err(`Fallback provider error (HTTP ${res.status})`, { status: res.status });
    return res.json();
  }

  let ctxCache = { at: 0, data: null };
  async function ctxs() {
    if (Date.now() - ctxCache.at < 3000 && ctxCache.data) return ctxCache.data;
    const [meta, list] = await info({ type: "metaAndAssetCtxs" });
    const map = new Map(meta.universe.map((u, i) => [u.name, list[i]]));
    ctxCache = { at: Date.now(), data: map };
    return map;
  }
  const normPremium = (c, ctx, t) => ({
    symbol: c, mark: num(ctx.markPx), index: num(ctx.oraclePx), indexLabel: "Oracle price",
    fundingRate: num(ctx.funding), fundingInterval: "1h",
    nextFundingTime: Math.ceil((t || Date.now()) / 3600e3) * 3600e3,   // funding settles hourly
    dataTime: t || Date.now(), source: SOURCE
  });

  const toCandle = (k) => ({ t: num(k.t), o: num(k.o), h: num(k.h), l: num(k.l), c: num(k.c), v: num(k.v), closeTime: num(k.T) });

  const Hyperliquid = {
    id: "hyperliquid",
    markets: ["futures"],
    sourceName: () => SOURCE,

    async candles(market, symbol, tf, limit = 200) {
      if (!INTERVALS[tf]) throw Err(`Unsupported timeframe: ${tf}`);
      const end = Date.now(), start = end - INTERVAL_MS[tf] * Math.min(1000, limit);
      const rows = await info({ type: "candleSnapshot", req: { coin: coin(symbol), interval: INTERVALS[tf], startTime: start, endTime: end } });
      // reuse Binance's validator by mapping to kline row shape
      const parsed = TA.Providers.binance.parseKlines((rows || []).map((k) => [k.t, k.o, k.h, k.l, k.c, k.v, k.T]), tf);
      return { ...parsed, source: SOURCE, fetchedAt: Date.now() };
    },

    async tickers(items) {
      const map = await ctxs();
      return items.map((x) => {
        const c = coin(x.symbol), ctx = map.get(c);
        if (!ctx) return null;
        const last = num(ctx.midPx ?? ctx.markPx), prev = num(ctx.prevDayPx);
        return { symbol: x.symbol, market: "Futures", last, change24h: ((last - prev) / prev) * 100, volume: num(ctx.dayNtlVlm), dataTime: Date.now(), source: SOURCE, priceLabel: "Mid price" };
      }).filter(Boolean);
    },

    async premium(symbol) {
      const c = coin(symbol), ctx = (await ctxs()).get(c);
      if (!ctx) throw Err(`${c} not listed on fallback provider`);
      return normPremium(c, ctx);
    },

    streamKlines(market, symbol, tf, onCandle, onStatus) {
      const c = coin(symbol);
      return openWs({ type: "candle", coin: c, interval: INTERVALS[tf] }, (m) => {
        if (m.channel !== "candle" || !m.data) return;
        const k = toCandle(m.data);
        if ([k.t, k.o, k.h, k.l, k.c, k.v].every(Number.isFinite) && k.h >= k.l) onCandle(k, false);
      }, onStatus);
    },

    streamPremium(symbol, onData, onStatus) {
      const c = coin(symbol);
      return openWs({ type: "activeAssetCtx", coin: c }, (m) => {
        if (m.channel === "activeAssetCtx" && m.data && m.data.ctx) onData(normPremium(c, m.data.ctx, Date.now()));
      }, onStatus);
    }
  };

  /** Same resilience rules as the Binance stream: backoff reconnect + stale timer. Sends a ping to keep the socket open. */
  function openWs(subscription, onMessage, onStatus = () => {}) {
    const STALE_MS = 60000; let ws, staleT, retryT, pingT, attempt = 0, closed = false, opened = false;
    const arm = () => { clearTimeout(staleT); staleT = setTimeout(() => { onStatus("stale"); try { ws.close(); } catch {} }, STALE_MS); };
    const connect = () => {
      if (closed) return;
      onStatus(opened ? "reconnecting" : "connecting", { attempt });
      try { ws = new WebSocket(WS); } catch { return schedule(); }
      ws.onopen = () => {
        attempt = 0; const re = opened; opened = true;
        ws.send(JSON.stringify({ method: "subscribe", subscription }));
        clearInterval(pingT); pingT = setInterval(() => { try { ws.send('{"method":"ping"}'); } catch {} }, 30000);
        onStatus("live", { reconnected: re }); arm();
      };
      ws.onmessage = (e) => { arm(); try { onMessage(JSON.parse(e.data)); } catch {} };
      ws.onclose = () => { clearTimeout(staleT); clearInterval(pingT); if (!closed) schedule(); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    const schedule = () => { clearTimeout(retryT); const d = Math.min(30000, 1000 * 2 ** attempt++) + Math.random() * 500; onStatus("reconnecting", { inMs: d }); retryT = setTimeout(connect, d); };
    connect();
    return { close() { closed = true; clearTimeout(staleT); clearTimeout(retryT); clearInterval(pingT); try { ws && ws.close(); } catch {} onStatus("closed"); } };
  }

  TA.Providers = TA.Providers || {};
  TA.Providers.hyperliquid = Hyperliquid;
})();
