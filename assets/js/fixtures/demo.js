/*
 * DEMO FIXTURES — illustrative only. NOT market data.
 * Isolated from production paths: services only read from here when demo mode is explicitly on,
 * and every value they return is tagged { source: "demo" } so the UI labels it.
 */
(function () {
  const TA = (window.TA = window.TA || {});

  // Deterministic PRNG so the sample chart looks the same on every load
  function rng(seed) { return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646; }

  function candles(n = 80, start = 100, seed = 7) {
    const r = rng(seed); const out = []; let p = start;
    const t0 = Date.now() - n * 3600e3;
    for (let i = 0; i < n; i++) {
      const drift = Math.sin(i / 11) * 0.35 + (i > n * 0.6 ? 0.25 : 0);
      const o = p, c = Math.max(1, o + (r() - 0.48 + drift * 0.3) * start * 0.012);
      const h = Math.max(o, c) + r() * start * 0.006, l = Math.min(o, c) - r() * start * 0.006;
      out.push({ t: t0 + i * 3600e3, o, h, l, c, v: 200 + r() * 800 });
      p = c;
    }
    return out;
  }

  TA.DEMO = {
    label: "Illustrative sample — not live market data",
    candles,
    watchlist: [
      { symbol: "BTC/USDT", market: "Spot", last: 64000.0, change24h: 1.2, volume: 1.8e9 },
      { symbol: "ETH/USDT", market: "Spot", last: 3100.0, change24h: -0.8, volume: 9.4e8 },
      { symbol: "SOL/USDT", market: "Futures", last: 140.0, change24h: 3.4, volume: 4.1e8 },
      { symbol: "BNB/USDT", market: "Spot", last: 560.0, change24h: 0.3, volume: 2.2e8 },
      { symbol: "XRP/USDT", market: "Futures", last: 0.52, change24h: -2.1, volume: 3.0e8 }
    ],
    signals: [
      {
        id: "demo-1", symbol: "SOL/USDT", market: "Futures", direction: "LONG", strategy: "Trend continuation",
        timeframe: "4H", createdAt: Date.now() - 42 * 60e3, source: "demo", dataSource: "Sample fixture",
        entry: [138.2, 139.6], stop: 134.9, targets: [143.5, 147.8], invalidation: "4H close below 134.9",
        score: 72, lifecycle: "active",
        supporting: ["Higher highs and higher lows on 4H", "Price reclaimed prior range high", "Funding rate near neutral"],
        conflicting: ["Daily RSI approaching overbought", "Volume below 20-period average"]
      },
      {
        id: "demo-2", symbol: "ETH/USDT", market: "Spot", direction: "SHORT", strategy: "Range rejection",
        timeframe: "1H", createdAt: Date.now() - 3 * 3600e3, source: "demo", dataSource: "Sample fixture",
        entry: [3125, 3140], stop: 3172, targets: [3070, 3035], invalidation: "1H close above 3172",
        score: 58, lifecycle: "triggered",
        supporting: ["Rejected at upper range boundary twice", "Bearish divergence on 1H momentum"],
        conflicting: ["Higher-timeframe trend still up", "Spot buying volume steady"]
      },
      {
        id: "demo-3", symbol: "BTC/USDT", market: "Spot", direction: "NO TRADE", strategy: "Structure check",
        timeframe: "1D", createdAt: Date.now() - 7 * 3600e3, source: "demo", dataSource: "Sample fixture",
        entry: null, stop: null, targets: [], invalidation: "Re-evaluate on daily close outside range",
        score: 31, lifecycle: "expired",
        supporting: ["Clear range between support and resistance"],
        conflicting: ["No confirmed break of structure", "Mixed signals across timeframes", "Event risk this week"]
      }
    ],
    trialUsed: 1
  };
})();
