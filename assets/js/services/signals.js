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

  // ---- Accounts (Milestone 7). The session token lives in localStorage; the server enforces the trial. ----
  const TOKEN_KEY = "ta-session";
  const getToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
  const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch {} };
  const authed = (url, opts = {}) => {
    const t = getToken();
    return fetch(url, { ...opts, headers: { ...(opts.headers || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) } });
  };
  const errText = async (res) => { try { const j = await res.json(); return typeof j.detail === "string" ? j.detail : (j.error && j.error.message) || (Array.isArray(j.detail) ? "Check the email and password (8+ characters)." : `HTTP ${res.status}`); } catch { return `HTTP ${res.status}`; } };

  TA.Auth = {
    available: () => Boolean(backend()),
    signedIn: () => Boolean(getToken()),
    user: null,
    async submit(kind, email, password) {
      const res = await authed(`${backend()}/api/auth/${kind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      if (!res.ok) return { ok: false, error: await errText(res) };
      const j = await res.json(); setToken(j.token); this.user = j.user;
      document.dispatchEvent(new CustomEvent("ta:auth"));
      return { ok: true, user: j.user };
    },
    async me() {
      if (!backend() || !getToken()) { this.user = null; return null; }
      try {
        const res = await authed(`${backend()}/api/auth/me`);
        if (res.status === 401) { this.signOut(); return null; }
        if (!res.ok) return this.user;
        return (this.user = await res.json());
      } catch { return this.user; }
    },
    async post(path, body) {
      try {
        const res = await authed(`${backend()}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        return res.ok ? { ok: true } : { ok: false, error: await errText(res) };
      } catch (e) { return { ok: false, error: e.message }; }
    },
    checkoutLink() {
      const P = window.TRADE_AI_CONFIG.pricing;
      if (!P.checkoutEnabled || !P.checkoutUrl || !this.user) return null;
      const u = new URL(P.checkoutUrl);
      u.searchParams.set("checkout[custom][user_id]", this.user.id);
      u.searchParams.set("checkout[email]", this.user.email);
      return u.toString();
    },
    signOut() { setToken(null); this.user = null; document.dispatchEvent(new CustomEvent("ta:auth")); }
  };
  const fromApi = (x) => ({
    id: x.id, symbol: x.symbol.replace(/USDT$/, "/USDT"), market: x.market === "futures" ? "Futures" : "Spot",
    direction: x.side, strategy: x.strategy.replace(/_/g, " "), strategyId: `${x.strategy} v${x.strategy_version}`,
    timeframe: x.timeframe, createdAt: Date.parse(x.generated_at), source: "live", dataSource: x.data_source,
    dataAsOf: x.data_as_of ? Date.parse(x.data_as_of) : null,
    entry: x.entry_low != null ? [x.entry_low, x.entry_high] : null, stop: x.stop ?? null, targets: x.targets || [],
    invalidation: x.invalidation || (x.reasons || []).join("; "), score: x.score ?? 0, lifecycle: x.lifecycle,
    supporting: (x.supporting || []).map((e) => `${e.factor}: ${e.detail}`), conflicting: (x.conflicting || []).map((e) => `${e.factor}: ${e.detail}`),
    explanation: x.explanation, rrNet: x.rr_net, assumptions: x.assumptions, locked: Boolean(x.locked)
  });
  TA.Signals_fromApi = fromApi;

  TA.Signals = {
    isConfigured: () => Boolean(cfg().signalsBaseUrl || backend()),
    LIFECYCLE: ["active", "triggered", "target_reached", "stopped", "expired", "invalidated"],

    async getRecent({ demo } = {}) {
      if (demo) { await wait(600); return { status: "ok", source: "demo", data: structuredClone(TA.DEMO.signals) }; }
      if (backend()) {
        try {
          const res = await authed(`${backend()}/api/signals?limit=50`);
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

    async getEvents(id) {
      if (!backend()) return { status: "disconnected", data: null };
      try {
        const res = await authed(`${backend()}/api/signals/${encodeURIComponent(id)}/events`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return { status: "ok", data: await res.json() };
      } catch (e) { return { status: "error", error: e.message, data: null }; }
    },

    async getAlerts(afterId = 0) {
      if (!backend()) return { status: "disconnected", data: null };
      try {
        const res = await authed(`${backend()}/api/alerts?after_id=${afterId}&limit=100`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return { status: "ok", data: (await res.json()).alerts };
      } catch (e) { return { status: "error", error: e.message, data: null }; }
    },

    async api(path) {
      if (!backend()) return { status: "disconnected", data: null };
      try {
        const res = await authed(`${backend()}${path}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return { status: "ok", data: await res.json() };
      } catch (e) { return { status: "error", error: e.message, data: null }; }
    },
    getPerformance(kind = "prospective") { return this.api(`/api/performance?kind=${kind}`); },
    getBacktests() { return this.api("/api/backtests"); },
    getBacktest(id) { return this.api(`/api/backtests/${encodeURIComponent(id)}`); },
    getHistory(offset = 0) { return this.api(`/api/signals/history?limit=50&offset=${offset}`); },

    async unlock(id) {
      if (!backend()) return { ok: false, error: "Not connected" };
      if (!getToken()) return { ok: false, needsAuth: true };
      try {
        const res = await authed(`${backend()}/api/signals/${encodeURIComponent(id)}/unlock`, { method: "POST" });
        if (res.status === 401) { TA.Auth.signOut(); return { ok: false, needsAuth: true }; }
        if (!res.ok) return { ok: false, status: res.status, error: await errText(res) };
        const j = await res.json();
        return { ok: true, signal: fromApi(j.signal), usage: j.usage };
      } catch (e) { return { ok: false, error: e.message }; }
    },

    async getUsage({ demo } = {}) {
      const limit = window.TRADE_AI_CONFIG.pricing.trialSignals;
      if (demo) return { status: "ok", source: "demo", data: { used: TA.DEMO.trialUsed, limit } };
      if (backend()) {
        if (!getToken()) return { status: "ok", source: "live", data: { used: null, limit, signedOut: true } };
        try {
          const res = await authed(`${backend()}/api/usage`);
          if (res.status === 401) { TA.Auth.signOut(); return { status: "ok", source: "live", data: { used: null, limit, signedOut: true } }; }
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const u = await res.json();
          return { status: "ok", source: "live", data: { used: u.used, limit: u.limit, plan: u.plan } };
        } catch (e) { return { status: "error", source: "live", data: { used: null, limit }, error: e.message }; }
      }
      if (!this.isConfigured()) return { status: "disconnected", source: "live", data: { used: null, limit } };
      try {
        const res = await fetch(`${cfg().signalsBaseUrl}/usage`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return { status: "ok", source: "live", data: await res.json() };
      } catch (e) { return { status: "error", source: "live", data: { used: null, limit }, error: e.message }; }
    }
  };
})();
