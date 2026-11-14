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
    backendBaseUrl: null,          // TRADE-AI API, e.g. "http://localhost:8000" — enables the API status indicator
    marketDataBaseUrl: null,       // e.g. "https://api.your-backend.example/v1/market"
    signalsBaseUrl: null,          // e.g. "https://api.your-backend.example/v1/signals"
    requestTimeoutMs: 8000,
    staleAfterSeconds: 60
  },

  auth: { enabled: false },        // no authentication integration yet

  links: {
    methodology: "#methodology",   // placeholder — replace with real pages
    risk: "#risk-disclosure",
    privacy: "#privacy",
    terms: "#terms",
    contact: "mailto:hello@example.com"
  }
};
