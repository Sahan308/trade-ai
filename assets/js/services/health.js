/*
 * Backend health service. Calls GET {backendBaseUrl}/health.
 * Result: { status: "not_configured" | "ok" | "degraded" | "unreachable", body?, checkedAt? }
 */
(function () {
  const TA = (window.TA = window.TA || {});
  TA.Health = {
    async check() {
      const base = window.TRADE_AI_CONFIG.api.backendBaseUrl;
      if (!base) return { status: "not_configured" };
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), window.TRADE_AI_CONFIG.api.backendTimeoutMs || window.TRADE_AI_CONFIG.api.requestTimeoutMs);
      try {
        const res = await fetch(`${base.replace(/\/$/, "")}/health`, { signal: ctrl.signal, headers: { Accept: "application/json" } });
        const body = await res.json().catch(() => null);
        if (res.ok && body && body.status === "ok") return { status: "ok", body, checkedAt: Date.now() };
        if (res.status === 503 || (body && body.status === "degraded")) return { status: "degraded", body, checkedAt: Date.now() };
        return { status: "unreachable", checkedAt: Date.now() };
      } catch {
        return { status: "unreachable", checkedAt: Date.now() };
      } finally { clearTimeout(t); }
    }
  };
})();
