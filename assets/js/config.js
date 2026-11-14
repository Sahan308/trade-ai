/*
 * TRADE-AI public runtime configuration.
 * Only non-secret values belong here — this file ships to the browser.
 * API keys must live on a backend; the frontend talks to YOUR backend, never to exchanges with keys.
 */
window.TRADE_AI_CONFIG = {
  brand: "TRADE-AI",

  // Pricing — the $20/month plan and 3-signal trial are confirmed.
  // Trial duration and renewal behaviour are NOT confirmed: leave null until the business decides.
  pricing: {
    currency: "USD",
    monthlyPrice: 20,
    trialSignals: 3,
    trialDurationDays: null,       // e.g. 7 — null renders "to be confirmed"
    renewalTerms: null,            // e.g. "Renews monthly until cancelled"
    checkoutEnabled: false         // no approved billing integration exists yet
  },

  // Backend endpoints. null = not connected; the UI shows designed disconnected states.
  api: {
    backendBaseUrl: null,
    // Public, key-less exchange data used directly from the browser when no backend is set.
    // Set to null to disable (the app then shows "not connected" states).
    publicProvider: "binance",
    // Used for Futures only when the primary provider is region-blocked or unreachable.
    futuresFallbackProvider: "hyperliquid",          // TRADE-AI API, e.g. "http://localhost:8000" — enables the API status indicator
    marketDataBaseUrl: null,       // e.g. "https://api.your-backend.example/v1/market"
    signalsBaseUrl: null,          // e.g. "https://api.your-backend.example/v1/signals"
    requestTimeoutMs: 8000,
    staleAfterSeconds: 30
  },

  // Symbols shown on the dashboard/watchlist (public market data only).
  watchlist: [
    { symbol: "BTC/USDT", market: "Spot" },
    { symbol: "ETH/USDT", market: "Spot" },
    { symbol: "SOL/USDT", market: "Futures" },
    { symbol: "BNB/USDT", market: "Spot" },
    { symbol: "XRP/USDT", market: "Futures" }
  ],
  watchlistRefreshSeconds: 15,

  // Shown wherever signals appear. Keep in sync with research/RESULTS.md.
  strategyStatus: {
    experimental: true,
    note: "Strategy smc_trend_pullback is experimental. In backtests on 8 coins over 2 years it lost money after fees on both 1H and 4H, and none of 15 tested variants passed. Signals are shown for research and transparency, not as recommendations.",
    url: "https://github.com/Sahan308/trade-ai/blob/main/research/RESULTS.md"
  },

  auth: { enabled: false },        // no authentication integration yet

  links: {
    methodology: "https://github.com/Sahan308/trade-ai/blob/main/research/RESULTS.md",
    risk: "#risk-disclosure",
    privacy: "#privacy",
    terms: "#terms",
    contact: "mailto:hello@example.com"
  }
};
