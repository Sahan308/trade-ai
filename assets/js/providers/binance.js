/*
 * Binance public market-data adapter (browser). No API key, read-only.
 * All Binance-specific URLs, payload shapes and limits live here — the rest of the app
 * talks to TA.MarketData, which can swap this for the TRADE-AI backend.
 *
 * Endpoints (verified 2026-11):
 *   Spot REST      https://data-api.binance.vision  (public market-data mirror)
 *   Spot WS        wss://data-stream.binance.vision/ws/<stream>
 *   Futures REST   https://fapi.binance.com         (USDⓈ-M)
 *   Futures WS     wss://fstream.binance.com/market/ws/<stream>
 */
(function () {
  const TA = (window.TA = window.TA || {});

  const HOSTS = {
    spot: { rest: "https://data-api.binance.vision", ws: "wss://data-stream.binance.vision/ws", name: "Binance Spot" },
    futures: { rest: "https://fapi.binance.com", ws: "wss://fstream.binance.com/market/ws", name: "Binance USDT-M Futures" }
  };
  const INTERVALS = { "1m": "1m", "5m": "5m", "15m": "15m", "1H": "1h", "4H": "4h", "1D": "1d" };
  const INTERVAL_MS = { "1m": 60e3, "5m": 300e3, "15m": 900e3, "1H": 3600e3, "4H": 14400e3, "1D": 86400e3 };
  const SYMBOL_RE = /^[A-Z0-9]{2,15}USDT$/;

  class ProviderError extends Error {
    constructor(message, { status, retryAfter, kind } = {}) { super(message); this.status = status; this.retryAfter = retryAfter; this.kind = kind; }
  }

  // ---- validation helpers ----
  const marketKey = (m) => {
    const k = String(m).toLowerCase();
    if (k !== "spot" && k !== "futures") throw new ProviderError(`Unsupported market type: ${m}`);
    return k;
  };
  const toSymbol = (s) => {
    const sym = String(s).toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!SYMBOL_RE.test(sym)) throw new ProviderError(`Invalid symbol: ${s}`);
    return sym;
  };
  const toInterval = (tf) => {
    if (!INTERVALS[tf]) throw new ProviderError(`Unsupported timeframe: ${tf}`);
    return INTERVALS[tf];
  };
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : NaN; };

  /** Parse + validate raw klines. Drops malformed rows, dedupes by open time, sorts, reports gaps. */
  function parseKlines(rows, tf) {
    const byTime = new Map(); let dropped = 0;
    for (const r of rows || []) {
      const c = { t: num(r[0]), o: num(r[1]), h: num(r[2]), l: num(r[3]), c: num(r[4]), v: num(r[5]), closeTime: num(r[6]) };
      const ok = [c.t, c.o, c.h, c.l, c.c, c.v].every(Number.isFinite) && c.h >= Math.max(c.o, c.c) && c.l <= Math.min(c.o, c.c) && c.v >= 0;
      if (!ok) { dropped++; continue; }
      byTime.set(c.t, c);                       // later duplicate wins
    }
    const candles = [...byTime.values()].sort((a, b) => a.t - b.t);
    const step = INTERVAL_MS[tf]; let gaps = 0;
    if (step) for (let i = 1; i < candles.length; i++) if (candles[i].t - candles[i - 1].t > step) gaps += Math.round((candles[i].t - candles[i - 1].t) / step) - 1;
    return { candles, dropped, gaps };
  }

  async function get(market, path, params) {
    const url = new URL(HOSTS[market].rest + path);
    Object.entries(params || {}).forEach(([k, v]) => url.searchParams.set(k, v));
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), (window.TRADE_AI_CONFIG?.api?.requestTimeoutMs) || 8000);
    let res;
    try { res = await fetch(url, { signal: ctrl.signal }); }
    catch (e) { throw new ProviderError(e.name === "AbortError" ? "Request timed out" : "Network error — provider unreachable", { kind: "network" }); }
    finally { clearTimeout(timer); }
    if (res.status === 429 || res.status === 418) throw new ProviderError("Rate limited by provider", { status: res.status, retryAfter: Number(res.headers.get("Retry-After")) || 60 });
    if (res.status === 451 || res.status === 403) throw new ProviderError("Provider not available in this region", { status: res.status, kind: "region" });
    if (!res.ok) throw new ProviderError(`Provider error (HTTP ${res.status})`, { status: res.status });
    return res.json();
  }

  const Binance = {
    id: "binance",
    INTERVALS: Object.keys(INTERVALS),
    sourceName: (market) => HOSTS[marketKey(market)].name,
    parseKlines, toSymbol,

    async candles(market, symbol, tf, limit = 200) {
      const m = marketKey(market), s = toSymbol(symbol), i = toInterval(tf);
      limit = Math.max(1, Math.min(1000, limit | 0));
      const rows = await get(m, m === "spot" ? "/api/v3/klines" : "/fapi/v1/klines", { symbol: s, interval: i, limit });
      return { ...parseKlines(rows, tf), source: HOSTS[m].name, fetchedAt: Date.now() };
    },

    /** 24h tickers. Spot: one batched request. Futures: one request per symbol (weight 1 each). */
    async tickers(items) {
      const spot = items.filter((x) => marketKey(x.market) === "spot"), fut = items.filter((x) => marketKey(x.market) === "futures");
      const out = [];
      if (spot.length) {
        const rows = await get("spot", "/api/v3/ticker/24hr", { symbols: JSON.stringify(spot.map((x) => toSymbol(x.symbol))) });
        for (const r of rows) out.push(normTicker(r, "Spot"));
      }
      const futRows = await Promise.all(fut.map((x) => get("futures", "/fapi/v1/ticker/24hr", { symbol: toSymbol(x.symbol) })));
      for (const r of futRows) out.push(normTicker(r, "Futures"));
      return out;
    },

    /** Most-traded USDT spot pairs by 24h quote volume (excludes stablecoin and leveraged-token pairs). */
    async topSpot(n = 25) {
      const rows = await get("spot", "/api/v3/ticker/24hr", { type: "MINI" });
      const skip = /^(USDC|FDUSD|TUSD|BUSD|DAI|USDP|USDE|EUR|AEUR|PAXG|WBTC|WBETH|BFUSD|XUSD|USD1|RLUSD)USDT$|(UP|DOWN|BULL|BEAR)USDT$/;
      return rows.filter((r) => r.symbol.endsWith("USDT") && !skip.test(r.symbol) && +r.quoteVolume > 0)
        .sort((a, b) => +b.quoteVolume - +a.quoteVolume).slice(0, n)
        .map((r) => ({ symbol: r.symbol.replace(/USDT$/, "/USDT"), last: +r.lastPrice, quoteVolume: +r.quoteVolume,
                       change: +r.openPrice ? ((+r.lastPrice - +r.openPrice) / +r.openPrice) * 100 : null }));
    },

    /** Contract specs: tick size, lot step, minimums, maintenance margin (futures). Cached for an hour. */
    async specs(market, symbol) {
      const m = marketKey(market), sym = toSymbol(symbol), key = `${m}:${m === "spot" ? sym : "*"}`;
      specCache[key] = specCache[key] && Date.now() - specCache[key].at < 3600e3 ? specCache[key]
        : { at: Date.now(), p: get(m, m === "spot" ? "/api/v3/exchangeInfo" : "/fapi/v1/exchangeInfo", m === "spot" ? { symbol: sym } : {}) };
      let info;
      try { info = await specCache[key].p; } catch (e) { delete specCache[key]; throw e; }
      const row = info.symbols.find((x) => x.symbol === sym);
      if (!row) throw new ProviderError(`${sym} is not listed on ${HOSTS[m].name}`);
      const f = Object.fromEntries(row.filters.map((x) => [x.filterType, x]));
      const mn = (f.NOTIONAL && f.NOTIONAL.minNotional) || (f.MIN_NOTIONAL && (f.MIN_NOTIONAL.minNotional || f.MIN_NOTIONAL.notional));
      return { symbol: sym, market: m, tick_size: num(f.PRICE_FILTER.tickSize), step_size: num(f.LOT_SIZE.stepSize), min_qty: num(f.LOT_SIZE.minQty),
        min_notional: mn ? num(mn) : null, mmr: row.maintMarginPercent ? num(row.maintMarginPercent) / 100 : null, source: HOSTS[m].name };
    },

    /** All USDT-M perpetuals: mark/index price, funding, plus 24h stats (2 requests). */
    async futuresBoard() {
      const [prem, tick, info, fi] = await Promise.all([get("futures", "/fapi/v1/premiumIndex", {}), get("futures", "/fapi/v1/ticker/24hr", {}),
        get("futures", "/fapi/v1/exchangeInfo", {}), get("futures", "/fapi/v1/fundingInfo", {}).catch(() => [])]);
      const t = Object.fromEntries(tick.map((x) => [x.symbol, x]));
      const crypto = new Set(info.symbols.filter((x) => x.contractType === "PERPETUAL" && x.status === "TRADING" && (!x.underlyingType || x.underlyingType === "COIN")).map((x) => x.symbol));
      const hours = Object.fromEntries(fi.map((x) => [x.symbol, +x.fundingIntervalHours || 8]));
      return prem.filter((r) => r.symbol.endsWith("USDT") && t[r.symbol] && crypto.has(r.symbol)).map((r) => ({
        intervalHours: hours[r.symbol] || 8,
        symbol: r.symbol, mark: num(r.markPrice), index: num(r.indexPrice), funding: num(r.lastFundingRate), nextFunding: +r.nextFundingTime,
        basis: num(r.indexPrice) ? (num(r.markPrice) - num(r.indexPrice)) / num(r.indexPrice) : null,
        change: num(t[r.symbol].priceChangePercent), quoteVolume: num(t[r.symbol].quoteVolume) }));
    },

    /** Per-symbol futures context: open interest history, funding history, long/short account ratios (1h buckets). */
    async futuresDetail(symbol, period = "1h", limit = 48) {
      const s = toSymbol(symbol), q = { symbol: s, period, limit };
      const [oi, fr, ls, top] = await Promise.all([
        get("futures", "/futures/data/openInterestHist", q), get("futures", "/fapi/v1/fundingRate", { symbol: s, limit: 30 }),
        get("futures", "/futures/data/globalLongShortAccountRatio", q).catch(() => []), get("futures", "/futures/data/topLongShortPositionRatio", q).catch(() => [])]);
      return {
        oi: oi.map((x) => ({ t: +x.timestamp, contracts: num(x.sumOpenInterest), usd: num(x.sumOpenInterestValue) })),
        funding: fr.map((x) => ({ t: +x.fundingTime, rate: num(x.fundingRate) })),
        accounts: ls.map((x) => ({ t: +x.timestamp, ratio: num(x.longShortRatio), long: num(x.longAccount) })),
        top: top.map((x) => ({ t: +x.timestamp, ratio: num(x.longShortRatio), long: num(x.longAccount) })),
        source: HOSTS.futures.name, fetchedAt: Date.now() };
    },

    /** Futures mark / index price and funding (premiumIndex). */
    async premium(symbol) {
      const r = await get("futures", "/fapi/v1/premiumIndex", { symbol: toSymbol(symbol) });
      return normPremium({ s: r.symbol, p: r.markPrice, i: r.indexPrice, r: r.lastFundingRate, T: r.nextFundingTime, E: r.time });
    },

    /**
     * Live kline stream with reconnect + stale detection.
     * onCandle(candle, isClosed); onStatus("connecting"|"live"|"stale"|"reconnecting"|"closed", info).
     * After every reconnect, onStatus("live", {reconnected:true}) — callers should reconcile via REST.
     */
    streamKlines(market, symbol, tf, onCandle, onStatus) {
      const m = marketKey(market), stream = `${toSymbol(symbol).toLowerCase()}@kline_${toInterval(tf)}`;
      return openStream(`${HOSTS[m].ws}/${stream}`, (msg) => {
        const k = msg.k; if (!k) return;
        const c = { t: num(k.t), o: num(k.o), h: num(k.h), l: num(k.l), c: num(k.c), v: num(k.v), closeTime: num(k.T), eventTime: num(msg.E) };
        if (![c.t, c.o, c.h, c.l, c.c, c.v].every(Number.isFinite) || c.h < c.l) return;   // ignore malformed
        onCandle(c, !!k.x);
      }, onStatus);
    },

    /** Futures mark/index/funding, pushed every second. */
    streamPremium(symbol, onData, onStatus) {
      return openStream(`${HOSTS.futures.ws}/${toSymbol(symbol).toLowerCase()}@markPrice@1s`, (msg) => {
        if (msg.e === "markPriceUpdate") onData(normPremium(msg));
      }, onStatus);
    }
  };

  const specCache = {};
  function normTicker(r, market) {
    return {
      symbol: `${r.symbol.replace(/USDT$/, "")}/USDT`, market, last: num(r.lastPrice), change24h: num(r.priceChangePercent),
      volume: num(r.quoteVolume), dataTime: num(r.closeTime), source: HOSTS[market === "Spot" ? "spot" : "futures"].name
    };
  }
  function normPremium(m) {
    return { symbol: m.s, mark: num(m.p), index: num(m.i), fundingRate: num(m.r), nextFundingTime: num(m.T), dataTime: num(m.E), source: HOSTS.futures.name };
  }

  /** Generic resilient WebSocket: exponential backoff, stale timer, clean close. */
  function openStream(url, onMessage, onStatus = () => {}) {
    const STALE_MS = 20000; let ws, staleTimer, retryTimer, attempt = 0, closed = false, everOpened = false;
    const armStale = () => {
      clearTimeout(staleTimer);
      staleTimer = setTimeout(() => { onStatus("stale"); try { ws.close(); } catch {} }, STALE_MS);
    };
    const connect = () => {
      if (closed) return;
      onStatus(everOpened ? "reconnecting" : "connecting", { attempt });
      try { ws = new WebSocket(url); } catch { return schedule(); }
      ws.onopen = () => { attempt = 0; const re = everOpened; everOpened = true; onStatus("live", { reconnected: re }); armStale(); };
      ws.onmessage = (e) => { armStale(); try { onMessage(JSON.parse(e.data)); } catch {} };
      ws.onclose = () => { clearTimeout(staleTimer); if (!closed) schedule(); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    const schedule = () => {
      clearTimeout(retryTimer);
      const delay = Math.min(30000, 1000 * 2 ** attempt++) + Math.random() * 500;
      onStatus("reconnecting", { inMs: delay });
      retryTimer = setTimeout(connect, delay);
    };
    connect();
    return { close() { closed = true; clearTimeout(staleTimer); clearTimeout(retryTimer); try { ws && ws.close(); } catch {} onStatus("closed"); } };
  }

  TA.Providers = TA.Providers || {};
  TA.Providers.binance = Binance;
  TA.ProviderError = ProviderError;
})();
