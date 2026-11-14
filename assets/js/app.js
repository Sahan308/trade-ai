/* App shell: hash router, views, states. */
(function () {
  const TA = window.TA, C = window.TRADE_AI_CONFIG;
  const $ = (s, r = document) => r.querySelector(s);
  TA.hydrateIcons();

  // ---------- State ----------
  const store = {
    get demo() { try { return sessionStorage.getItem("ta-demo") === "1"; } catch { return false; } },
    set demo(v) { try { sessionStorage.setItem("ta-demo", v ? "1" : "0"); } catch {} }
  };
  if (new URLSearchParams(location.search).get("demo") === "1") store.demo = true;
  const ui = { tf: "4H", ema: true, volume: true };
  let lastSignals = [];

  // ---------- Routes ----------
  const ROUTES = [
    { group: "Overview" },
    { id: "dashboard", label: "Dashboard", icon: "grid", ready: true },
    { id: "markets", label: "Market overview", icon: "globe", ready: true },
    { id: "watchlist", label: "Watchlist", icon: "star", ready: true },
    { group: "Analysis" },
    { id: "signals", label: "Signals", icon: "zap", ready: true },
    { id: "chart", label: "Advanced chart", icon: "candles", ready: true },
    { id: "scanner", label: "Market scanner", icon: "radar" },
    { id: "patterns", label: "Pattern & SMC", icon: "layers" },
    { id: "futures", label: "Futures intelligence", icon: "chart" },
    { group: "Performance & risk" },
    { id: "history", label: "Signal history", icon: "history", ready: true },
    { id: "risk", label: "Risk manager", icon: "gauge", ready: true },
    { group: "Settings" },
    { id: "alerts", label: "Alerts", icon: "bell" },
    { id: "account", label: "Account", icon: "user" },
    { id: "billing", label: "Billing", icon: "card", ready: true }
  ];
  const byId = Object.fromEntries(ROUTES.filter((r) => r.id).map((r) => [r.id, r]));

  $("#sideNav").innerHTML = ROUTES.map((r) => r.group
    ? `<div class="side-label">${r.group}</div>`
    : `<a class="side-link" href="#/${r.id}" data-route="${r.id}">${TA.icon(r.icon)}${r.label}${r.ready ? "" : '<span class="soon">Soon</span>'}</a>`).join("");
  $("#bottomNav").innerHTML = ["dashboard", "signals", "chart", "risk"].map((id) =>
    `<a href="#/${id}" data-route="${id}">${TA.icon(byId[id].icon)}${byId[id].label.split(" ")[0]}</a>`).join("") +
    `<a href="#" id="moreBtn" role="button" aria-controls="sidebar">${TA.icon("menu")}More</a>`;

  // ---------- Mobile drawer ----------
  const sb = $("#sidebar"), scrim = $("#scrim"), menuBtn = $("#menuBtn");
  const drawer = (open) => { sb.classList.toggle("open", open); scrim.classList.toggle("show", open); menuBtn.setAttribute("aria-expanded", open); if (open) sb.querySelector("a").focus(); };
  menuBtn.addEventListener("click", () => drawer(true));
  scrim.addEventListener("click", () => drawer(false));
  $("#moreBtn").addEventListener("click", (e) => { e.preventDefault(); drawer(true); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && sb.classList.contains("open")) { drawer(false); menuBtn.focus(); } });

  // ---------- Connection indicator ----------
  function renderConn(extra) {
    const el = $("#conn");
    if (store.demo) { el.className = "conn demo"; el.innerHTML = `<span class="dot"></span>Sample data<span>&nbsp;· not live</span>`; }
    else if (TA.MarketData.isConfigured()) { el.className = "conn live"; el.innerHTML = `<span class="dot dot-live"></span>Connected<span>${extra ? " · " + extra : ""}</span>`; }
    else { el.className = "conn off"; el.innerHTML = `${TA.icon("wifiOff", "icon-sm")}No data feed<span>&nbsp;· not configured</span>`; }
    $("#demoBanner").hidden = !store.demo;
  }
  const demoToggle = $("#demoToggle");
  demoToggle.checked = store.demo;
  demoToggle.addEventListener("change", () => { store.demo = demoToggle.checked; renderConn(); route(); });

  // ---------- Shared state blocks ----------
  const state = (kind, title, body, actions = "") => {
    const icon = { off: "plug", error: "alert", empty: "search", soon: "flask" }[kind] || "info";
    return `<div class="state ${kind}" role="${kind === "error" ? "alert" : "status"}"><div class="ic">${TA.icon(icon, "icon-lg")}</div><h3>${title}</h3><p>${body}</p>${actions ? `<div class="actions">${actions}</div>` : ""}</div>`;
  };
  const demoBtn = `<button class="btn btn-sm" data-act="demo-on">${TA.icon("flask", "icon-sm")}View sample preview</button>`;
  const retryBtn = `<button class="btn btn-sm" data-act="retry">${TA.icon("refresh", "icon-sm")}Retry</button>`;
  const disconnected = (what) => state("off", `${what} isn't connected`, "No market data API is configured, so nothing is shown rather than made-up numbers. Set <code>api.marketDataBaseUrl</code> in <code>config.js</code> once the backend exists.", demoBtn);
  const fromResult = (r, what, render) => {
    if (r.status === "disconnected") return disconnected(what);
    if (r.status === "error") return state("error", `Couldn't load ${what.toLowerCase()}`, `The request failed (${TA.esc(r.error || "unknown error")}). Check the API and try again.`, retryBtn);
    if (r.status === "empty") return state("empty", `No ${what.toLowerCase()} yet`, "The feed is connected but returned nothing.");
    return render(r.data);
  };

  // ---------- Pieces ----------
  const skRows = (n, cols) => Array.from({ length: n }, () => `<tr class="sk-row">${Array.from({ length: cols }, () => `<td><div class="skeleton" style="width:${50 + Math.random() * 40}%"></div></td>`).join("")}</tr>`).join("");
  const wlTable = (rows, demo) => `<div class="table-wrap"><table>
      <caption class="sr-only">Watchlist${demo ? " — sample data" : ""}</caption>
      <thead><tr><th scope="col">Symbol</th><th scope="col">Market</th><th scope="col" class="r">${demo ? "Sample price" : "Last price"}</th><th scope="col" class="r">24h</th><th scope="col" class="r">Volume</th></tr></thead>
      <tbody>${rows || skRows(5, 5)}</tbody></table></div>`;
  const wlRows = (data) => data.map((d) => `<tr><th scope="row" style="font-weight:600">${TA.esc(d.symbol)}</th><td><span class="badge">${d.market}</span></td><td class="r num">${TA.fmtPrice(d.last)}</td><td class="r">${TA.chg(d.change24h)}</td><td class="r num">${TA.fmtCompact(d.volume)}</td></tr>`).join("");

  const chartControls = () => `
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
      <div class="seg" role="group" aria-label="Timeframe">${["15m", "1H", "4H", "1D"].map((t) => `<button type="button" data-tf="${t}" aria-pressed="${ui.tf === t}">${t}</button>`).join("")}</div>
      <div class="chips" role="group" aria-label="Indicators">
        <button type="button" class="chip" data-ind="ema" aria-pressed="${ui.ema}"><span class="term" data-tip="Exponential moving average — a trend line weighted toward recent prices." tabindex="-1">EMA 20</span></button>
        <button type="button" class="chip" data-ind="volume" aria-pressed="${ui.volume}">Volume</button>
      </div>
    </div>`;

  async function loadChart(host) {
    const area = host.querySelector(".chart-area");
    area.innerHTML = `<div class="skeleton" style="position:absolute;inset:12px"></div>`;
    const r = await TA.MarketData.getCandles("SOL/USDT", ui.tf, { demo: store.demo });
    if (!host.isConnected) return;
    area.innerHTML = fromResult(r, "Chart data", (cs) => TA.candleChart(cs, { w: 900, h: 340, ema: ui.ema, volume: ui.volume, cls: "chart-anim" }));
    // trigger line draw
    requestAnimationFrame(() => area.querySelectorAll(".draw").forEach((p) => p.classList.add("go")));
    area.querySelectorAll(".candle").forEach((c) => (c.style.opacity = 1, c.style.transform = "none"));
    const meta = host.querySelector(".chart-meta");
    if (meta) meta.innerHTML = r.status === "ok" ? `${r.source === "demo" ? '<span class="badge badge-demo">Sample</span> ' : ""}<span class="muted" style="font-size:.8rem">Updated ${TA.fmtTime(r.fetchedAt)}</span>` : "";
  }
  function chartPanel(title = "Primary chart") {
    return `<section class="card panel" data-chart>
      <div class="panel-head"><h2>${TA.icon("candles")}${title} <span class="muted" style="font-weight:500;font-size:.85rem">· ${store.demo ? "SAMPLE/USDT" : "No symbol"}</span></h2>${chartControls()}</div>
      <div class="chart-area"></div><div class="chart-meta" style="margin-top:10px"></div></section>`;
  }

  // ---------- Views ----------
  const views = {
    async dashboard(el) {
      el.innerHTML = `
        <div class="status-row">
          <div class="card stat"><small>Market status</small><strong id="mkStatus">${store.demo ? "Sample" : "Unknown"}</strong><p class="muted">${store.demo ? "Preview fixture" : "Needs data feed"}</p></div>
          <div class="card stat"><small>Data connection</small><strong>${store.demo ? `<span class="dot" style="color:var(--accent)"></span>Sample` : TA.MarketData.isConfigured() ? `<span class="dot dot-live" style="color:var(--info)"></span>Live` : `${TA.icon("wifiOff", "icon-sm")}Offline`}</strong><p class="muted">${store.demo ? "Fixture — not live" : "api.marketDataBaseUrl"}</p></div>
          <div class="card stat"><small>Data freshness</small><strong id="fresh">—</strong><p class="muted">Stale after ${C.api.staleAfterSeconds}s</p></div>
          <div class="card stat"><small>Trial signals</small><strong id="usageTxt"><span class="skeleton" style="width:60px;display:inline-block">&nbsp;</span></strong><div class="usage" id="usageBar" aria-hidden="true"></div></div>
        </div>
        <div class="grid-dash">
          <div class="span-8">${chartPanel()}</div>
          <section class="card panel span-4"><div class="panel-head"><h2>${TA.icon("zap")}Recent signals</h2><a class="btn btn-ghost btn-sm" href="#/signals">View all</a></div><div id="recent" class="list-signals">${Array.from({ length: 3 }, () => '<div class="skeleton" style="height:58px;border-radius:12px"></div>').join("")}</div></section>
          <section class="card panel span-12"><div class="panel-head"><h2>${TA.icon("star")}Watchlist</h2></div><div id="wl">${wlTable(null)}</div></section>
        </div>`;
      loadChart(el.querySelector("[data-chart]"));

      const [wl, sig, use] = await Promise.all([
        TA.MarketData.getWatchlist({ demo: store.demo }), TA.Signals.getRecent({ demo: store.demo }), TA.Signals.getUsage({ demo: store.demo })
      ]);
      if (!el.isConnected) return;
      if (sig.status === "ok") lastSignals = sig.data;
      $("#wl", el).innerHTML = fromResult(wl, "Watchlist data", (d) => wlTable(wlRows(d), wl.source === "demo"));
      $("#fresh", el).textContent = wl.fetchedAt ? TA.ago(wl.fetchedAt) : "No data";
      $("#recent", el).innerHTML = sig.status === "disconnected"
        ? state("off", "No signal feed", "Signals appear here once an approved signal backend is connected.", demoBtn)
        : fromResult(sig, "Signals", (d) => d.map((s) => `<button class="sig-row" data-sig="${s.id}">${TA.dirBadge(s.direction)}<span><b>${TA.esc(s.symbol)}</b><br/><span class="muted" style="font-size:.8rem">${s.timeframe} · ${TA.lifeLabel[s.lifecycle]}</span></span><span class="muted" style="font-size:.78rem">${TA.ago(s.createdAt)}</span></button>`).join("") + (sig.source === "demo" ? `<p class="demo-stamp" style="margin:4px 0 0">${TA.icon("flask", "icon-sm")}Illustrative examples</p>` : ""));
      const u = use.data;
      $("#usageTxt", el).innerHTML = u.used == null ? `— <span class="muted" style="font-size:.85rem">of ${u.limit}</span>` : `${u.used} <span class="muted" style="font-size:.85rem">of ${u.limit} used${use.source === "demo" ? " (sample)" : ""}</span>`;
      $("#usageBar", el).innerHTML = Array.from({ length: u.limit }, (_, i) => `<i class="${u.used != null && i < u.used ? "used" : ""}"></i>`).join("");
    },

    async markets(el) {
      el.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("globe")}Market overview</h2><span class="muted" style="font-size:.85rem">Spot &amp; Futures</span></div><div id="m">${wlTable(null)}</div></section>`;
      const r = await TA.MarketData.getWatchlist({ demo: store.demo });
      if (el.isConnected) $("#m", el).innerHTML = fromResult(r, "Market data", (d) => wlTable(wlRows(d), r.source === "demo"));
    },

    async watchlist(el) {
      el.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("star")}Your watchlist</h2><button class="btn btn-sm" aria-disabled="true" title="Requires accounts">${TA.icon("plus", "icon-sm")}Add symbol</button></div>
        <div class="integration" style="margin-bottom:14px">${TA.icon("info", "icon-sm")}<span>Saving symbols needs accounts and a backend. Adding is disabled until then.</span></div><div id="w">${wlTable(null)}</div></section>`;
      const r = await TA.MarketData.getWatchlist({ demo: store.demo });
      if (el.isConnected) $("#w", el).innerHTML = fromResult(r, "Watchlist data", (d) => wlTable(wlRows(d), r.source === "demo"));
    },

    async signals(el) {
      let filter = "ALL";
      el.innerHTML = `<div class="panel-head" style="margin:0"><div class="seg" role="group" aria-label="Filter by direction">${["ALL", "LONG", "SHORT", "NO TRADE"].map((f) => `<button data-f="${f}" aria-pressed="${f === filter}">${f === "ALL" ? "All" : f[0] + f.slice(1).toLowerCase()}</button>`).join("")}</div></div>
        <div id="sg" class="module-grid">${Array.from({ length: 3 }, () => '<div class="skeleton" style="height:320px;border-radius:18px"></div>').join("")}</div>`;
      const r = await TA.Signals.getRecent({ demo: store.demo });
      if (!el.isConnected) return;
      if (r.status === "ok") lastSignals = r.data;
      const draw = () => {
        const host = $("#sg", el);
        if (r.status !== "ok") { host.style.display = "block"; host.innerHTML = `<div class="card">${r.status === "disconnected" ? state("off", "No signal feed connected", "TRADE-AI doesn't generate signals in the browser. They'll appear here once an approved signal backend is connected.", demoBtn) : fromResult(r, "Signals")}</div>`; return; }
        const list = r.data.filter((s) => filter === "ALL" || s.direction === filter);
        host.innerHTML = list.length ? list.map((s, i) => `<div class="reveal" style="--d:${i * 60}ms" data-sig="${s.id}" role="button" tabindex="0" aria-label="Open ${TA.esc(s.symbol)} details">${TA.signalCard(s)}</div>`).join("") : `<div class="card" style="grid-column:1/-1">${state("empty", "Nothing matches this filter", "Try another direction.")}</div>`;
        TA.initReveal(host);
      };
      el.querySelectorAll("[data-f]").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; el.querySelectorAll("[data-f]").forEach((x) => x.setAttribute("aria-pressed", x === b)); draw(); }));
      draw();
    },

    chart(el) { el.innerHTML = chartPanel("Advanced chart") + `<div class="integration">${TA.icon("info", "icon-sm")}<span>Drawing tools, symbol search and level overlays need the market data backend.</span></div>`; loadChart(el.querySelector("[data-chart]")); },

    history(el) {
      el.innerHTML = `<div class="grid-dash">
        <section class="card panel span-6 measured" style="border-left-width:3px"><div class="panel-head"><h2>${TA.icon("database")}Measured performance</h2><span class="badge badge-info">Tracked outcomes only</span></div>
          ${state("empty", "No resolved signals yet", "Win rate, average R and outcome breakdowns appear only once real signals are recorded and resolved. Nothing is estimated here.")}</section>
        <section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("flask")}Unvalidated estimates</h2><span class="badge badge-demo">Not measured</span></div>
          <p style="font-size:.9rem">Setup scores are heuristics. They'll stay in this separate column — never mixed into measured results — until there's enough history to check them.</p></section>
        <section class="card panel span-12"><div class="panel-head"><h2>${TA.icon("history")}Signal log</h2></div>
          <div class="table-wrap"><table><thead><tr><th>Time</th><th>Symbol</th><th>Direction</th><th>Lifecycle</th><th class="r">Result</th></tr></thead>
          <tbody><tr><td colspan="5">${state("off", "History backend not connected", "Every signal and its outcome will be listed here, losses included.")}</td></tr></tbody></table></div></section></div>`;
    },

    risk(el) {
      el.innerHTML = `<div class="grid-dash">
        <section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("gauge")}Position size calculator</h2><span class="badge badge-info">Works offline</span></div>
          <form id="rf" class="form-grid" novalidate>
            ${fld("bal", "Account balance (USD)", 1000, "Funds you're willing to put at risk in this account.")}
            ${fld("riskPct", "Risk per trade (%)", 1, "Common practice is 0.5–2%.")}
            ${fld("entry", "Entry price", "", "Your planned entry.")}
            ${fld("stop", "Stop-loss price", "", "Where the idea is wrong.")}
            ${fld("lev", "Leverage (Futures)", 1, "1 for Spot.")}
            <div class="field"><label for="side">Direction</label><select id="side"><option>LONG</option><option>SHORT</option></select><span class="err" id="e-side"></span></div>
            <div style="grid-column:1/-1"><button class="btn btn-primary" type="submit">Calculate</button></div>
          </form></section>
        <section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("target")}Result</h2></div><div id="rr" aria-live="polite">${state("empty", "Enter your numbers", "Results use only what you type in. No market data is needed.")}</div></section></div>`;
      function fld(id, label, val, hint) { return `<div class="field"><label for="${id}">${label}</label><input id="${id}" inputmode="decimal" value="${val}" aria-describedby="h-${id} e-${id}"/><span class="hint" id="h-${id}">${hint}</span><span class="err" id="e-${id}"></span></div>`; }
      $("#rf", el).addEventListener("submit", (e) => {
        e.preventDefault();
        const v = (id) => parseFloat($("#" + id, el).value);
        const vals = { bal: v("bal"), riskPct: v("riskPct"), entry: v("entry"), stop: v("stop"), lev: v("lev") }, side = $("#side", el).value;
        let ok = true;
        const err = (id, m) => { $("#e-" + id, el).textContent = m; $("#" + id, el).setAttribute("aria-invalid", m ? "true" : "false"); if (m) ok = false; };
        Object.entries(vals).forEach(([k, x]) => err(k, !(x > 0) ? "Enter a number above 0." : ""));
        if (ok && vals.riskPct > 100) err("riskPct", "Must be 100 or less.");
        if (ok && side === "LONG" && vals.stop >= vals.entry) err("stop", "For a long, the stop must be below entry.");
        if (ok && side === "SHORT" && vals.stop <= vals.entry) err("stop", "For a short, the stop must be above entry.");
        if (!ok) { $("#rr", el).innerHTML = state("error", "Check the highlighted fields", "Fix the inputs and calculate again."); return; }
        const riskUsd = vals.bal * vals.riskPct / 100, dist = Math.abs(vals.entry - vals.stop), qty = riskUsd / dist, notional = qty * vals.entry, margin = notional / vals.lev;
        const R = (m) => `<div class="result"><small>${m[0]}</small><div>${m[1]}</div></div>`;
        $("#rr", el).innerHTML = `<div class="result-grid">${[["Amount at risk", TA.fmtUsd(riskUsd)], ["Stop distance", `${TA.fmtPrice(dist)} (${(dist / vals.entry * 100).toFixed(2)}%)`], ["Position size", `${qty.toPrecision(5)} units`], ["Notional value", TA.fmtUsd(notional)], ["Margin required", TA.fmtUsd(margin)], ["1R target (" + side.toLowerCase() + ")", TA.fmtPrice(side === "LONG" ? vals.entry + dist : vals.entry - dist)]].map(R).join("")}</div>
          ${margin > vals.bal ? `<p class="down" style="margin:12px 0 0;font-size:.86rem">${TA.icon("alert", "icon-sm")} Margin exceeds your balance at this leverage.</p>` : ""}
          <p class="muted" style="font-size:.78rem;margin:12px 0 0">Doesn't include fees, slippage or funding. Not financial advice.</p>`;
        TA.toast("Position size calculated", "check");
      });
    },

    billing(el) {
      const P = C.pricing;
      el.innerHTML = `<div class="grid-dash"><section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("card")}Plan</h2><span class="badge">Trial</span></div>
        <p style="font-size:1.6rem;font-family:var(--font-display);color:var(--tx-1);margin:0">$${P.monthlyPrice} <span class="muted" style="font-size:.9rem">USD / month after trial</span></p>
        <dl class="detail-grid" style="grid-template-columns:1fr 1fr;margin:16px 0">
          <div class="level"><dt>Trial signals</dt><dd>${P.trialSignals}</dd></div>
          <div class="level"><dt>Trial length</dt><dd>${P.trialDurationDays ? P.trialDurationDays + " days" : "To be confirmed"}</dd></div>
          <div class="level" style="grid-column:1/-1"><dt>Renewal</dt><dd style="font-family:var(--font-sans)">${P.renewalTerms || "To be confirmed"}</dd></div></dl>
        <button class="btn btn-primary" aria-disabled="true" id="upg">Upgrade</button></section>
        <section class="card panel span-6">${state("off", "Billing isn't connected", "No payment provider is set up, so no card details are collected. Checkout will be added once a billing integration is approved.")}</section></div>`;
      $("#upg", el).addEventListener("click", () => TA.toast("Checkout isn't available yet.", "info"));
    }
  };

  const soonCopy = {
    scanner: ["Market scanner", "Filter pairs by structure, momentum and volume. Needs the market data backend and a scanning service."],
    patterns: ["Pattern & SMC analysis", "Detected patterns, order blocks and liquidity zones, each with the reasoning behind it. Needs an approved analysis service."],
    futures: ["Futures intelligence", "Funding, open interest and liquidation context for perpetual contracts. Needs a derivatives data source."],
    alerts: ["Alerts", "Notifications when a signal triggers, hits a target or is invalidated. Needs accounts and a notification service."],
    account: ["Account", "Profile, security and preferences. Sign-in isn't connected yet."]
  };
  Object.keys(soonCopy).forEach((id) => (views[id] = (el) => {
    const [t, d] = soonCopy[id];
    el.innerHTML = `<section class="card">${state("soon", `${t} — not available yet`, d, `<a class="btn btn-sm" href="#/dashboard">Back to dashboard</a>`)}</section>`;
  }));

  // ---------- Router ----------
  let current;
  function route() {
    const id = (location.hash.match(/^#\/([\w-]+)/) || [])[1] || "dashboard";
    const r = byId[id] || byId.dashboard;
    current = r.id;
    document.querySelectorAll("[data-route]").forEach((a) => a.dataset.route === r.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    $("#viewTitle").textContent = r.label;
    document.title = `${r.label} · TRADE-AI`;
    const host = $("#content");
    const view = document.createElement("div");
    view.className = "view"; view.style.display = "grid"; view.style.gap = "16px";
    host.replaceChildren(view);
    views[r.id](view);
    drawer(false);
  }
  window.addEventListener("hashchange", () => { route(); $("#content").focus({ preventScroll: true }); window.scrollTo(0, 0); });

  // ---------- Delegated actions ----------
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act],[data-tf],[data-ind],[data-sig]");
    if (!t) return;
    if (t.dataset.act === "demo-on") { demoToggle.checked = true; store.demo = true; renderConn(); route(); }
    else if (t.dataset.act === "retry") route();
    else if (t.dataset.tf || t.dataset.ind) {
      const panel = t.closest("[data-chart]");
      if (t.dataset.tf) { ui.tf = t.dataset.tf; panel.querySelectorAll("[data-tf]").forEach((b) => b.setAttribute("aria-pressed", b === t)); }
      else { ui[t.dataset.ind] = !ui[t.dataset.ind]; t.setAttribute("aria-pressed", ui[t.dataset.ind]); }
      loadChart(panel);
    } else if (t.dataset.sig) {
      const s = lastSignals.find((x) => x.id === t.dataset.sig);
      if (s) TA.modal.open(TA.signalDetail(s));
    }
  });
  document.addEventListener("keydown", (e) => {
    const t = e.target.closest && e.target.closest('[data-sig][role="button"]');
    if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); t.click(); }
  });

  renderConn();
  route();
})();
