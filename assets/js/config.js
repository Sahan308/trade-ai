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
    trialSignals: 3,   // legacy
    trialDays: 7,      // Pro trial on sign-up (server: TRADEAI_TRIAL_DAYS)
    trialDurationDays: null,       // e.g. 7 — null renders "to be confirmed"
    renewalTerms: null,            // e.g. "Renews monthly until cancelled"
    checkoutEnabled: false,        // OFF until Lemon Squeezy identity verification + live mode (test mode would let anyone use the test card)
    // Lemon Squeezy hosted checkout link for the $20/month variant, e.g.
    // "https://YOURSTORE.lemonsqueezy.com/buy/xxxxxxxx-xxxx-…". Card details are entered only on Lemon Squeezy.
    checkoutUrl: "https://tradeai.lemonsqueezy.com/checkout/buy/e661d5af-0da0-45d7-b6a4-0b513215e261"
  },

  // Backend endpoints. null = not connected; the UI shows designed disconnected states.
  api: {
    backendBaseUrl: "https://gku4jfhdjmk2.ample.run",
    // Public, key-less exchange data used directly from the browser when no backend is set.
    // Set to null to disable (the app then shows "not connected" states).
    publicProvider: "binance",
    // Used for Futures only when the primary provider is region-blocked or unreachable.
    futuresFallbackProvider: "hyperliquid",          // TRADE-AI API, e.g. "http://localhost:8000" — enables the API status indicator
    marketDataBaseUrl: null,       // e.g. "https://api.your-backend.example/v1/market"
    signalsBaseUrl: null,          // e.g. "https://api.your-backend.example/v1/signals"
    requestTimeoutMs: 8000,
    backendTimeoutMs: 60000,       // free hosting can take ~30–50s to wake up
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
    note: "Signals are experimental. Strategy smc_trend_pullback lost money after fees in backtests on 8 coins, and across four pre-registered research rounds (25 variants, including breakout, trend, momentum and mean-reversion strategies) none passed out-of-sample testing (round 4 included a published portfolio trend-following method). Signals are shown for research and transparency, not as recommendations.",
    url: "https://github.com/Sahan308/trade-ai/blob/main/research/RESULTS.md"
  },

  auth: { enabled: false },        // no authentication integration yet

  links: {
    methodology: "https://github.com/Sahan308/trade-ai/blob/main/research/RESULTS.md",
    risk: "legal/risk.html",
    privacy: "legal/privacy.html",
    terms: "legal/terms.html",
    contact: "https://github.com/Sahan308/trade-ai/issues"
  }
};
