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
  const ui = { tf: "1H", ema: true, volume: true, sym: 0, sma50: false, bb: false, vwap: false, st: false, psar: false, ichi: false, pat: true, smc: false };
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
    { id: "scanner", label: "Market scanner", icon: "radar", ready: true },
    { id: "patterns", label: "Pattern & SMC", icon: "layers", ready: true },
    { id: "futures", label: "Futures intelligence", icon: "chart", ready: true },
    { group: "Performance & risk" },
    { id: "monitor", label: "Market risk monitor", icon: "shield", ready: true },
    { id: "history", label: "Signal history", icon: "history", ready: true },
    { id: "risk", label: "Risk manager", icon: "gauge", ready: true },
    { group: "Settings" },
    { id: "alerts", label: "Alerts", icon: "bell", ready: true },
    { id: "account", label: "Account", icon: "user", ready: true },
    { id: "billing", label: "Billing", icon: "card", ready: true }
  ];
  const byId = Object.fromEntries(ROUTES.filter((r) => r.id).map((r) => [r.id, r]));
  byId.stats = { id: "stats", label: "Usage stats", icon: "chart", ready: true };   // admin-only, not in the menu
  byId.reset = { id: "reset", label: "Reset password", icon: "user", ready: true }; // opened from the reset email

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

  // ---------- Live resources (streams/timers), closed on every route change ----------
  const live = new Set();
  const track = (h) => { if (h) live.add(h); return h; };
  const closeLive = () => { live.forEach((h) => { try { h.close(); } catch {} }); live.clear(); };
  const every = (ms, fn) => { const id = setInterval(() => { if (!document.hidden) fn(); }, ms); return track({ close: () => clearInterval(id) }); };

  // Freshness: any element with data-ts shows its age and turns red when stale.
  const ageHtml = (ts) => `<span data-ts="${ts}">${TA.ago(ts)}</span>`;
  setInterval(() => document.querySelectorAll("[data-ts]").forEach((el) => {
    const ts = +el.dataset.ts; if (!ts) return;
    const stale = (Date.now() - ts) / 1000 > C.api.staleAfterSeconds;
    el.textContent = TA.ago(ts) + (stale ? " · stale" : "");
    el.classList.toggle("down", stale);
  }), 1000);

  // ---------- Connection indicator ----------
  function renderConn() {
    const el = $("#conn"), m = TA.MarketData.mode(store.demo);
    if (m === "demo") { el.className = "conn demo"; el.innerHTML = `<span class="dot"></span>Sample data<span>&nbsp;· not live</span>`; }
    else if (m === "provider") { el.className = "conn live"; el.innerHTML = `<span class="dot dot-live"></span>Binance<span>&nbsp;· public data, read-only</span>`; }
    else if (m === "backend") { el.className = "conn live"; el.innerHTML = `<span class="dot dot-live"></span>TRADE-AI API<span>&nbsp;· read-only</span>`; }
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
  const strategyNotice = () => C.strategyStatus && C.strategyStatus.experimental
    ? `<div class="integration" role="note" style="border-color:rgba(241,107,117,.45)"><span class="down">${TA.icon("alert", "icon-sm")}</span><span>${TA.esc(C.strategyStatus.note)} <a href="${C.strategyStatus.url}" target="_blank" rel="noopener" style="text-decoration:underline">Read the research</a></span></div>` : "";
  TA.strategyNotice = strategyNotice;
  const demoBtn = `<button class="btn btn-sm" data-act="demo-on">${TA.icon("flask", "icon-sm")}View sample preview</button>`;
  const retryBtn = `<button class="btn btn-sm" data-act="retry">${TA.icon("refresh", "icon-sm")}Retry</button>`;
  const disconnected = (what) => state("off", `${what} isn't connected`, "No market data source is configured, so nothing is shown rather than made-up numbers. Set <code>api.publicProvider</code> or <code>api.backendBaseUrl</code> in <code>config.js</code>.", demoBtn);
  const fromResult = (r, what, render) => {
    if (r.status === "disconnected") return disconnected(what);
    if (r.status === "error") return state("error", `Couldn't load ${what.toLowerCase()}`, `${TA.esc(r.error || "Unknown error")}.${r.retryAfter ? ` Try again in about ${r.retryAfter}s.` : " Check your connection and try again."}`, retryBtn);
    if (r.status === "empty") return state("empty", `No ${what.toLowerCase()} yet`, "The feed is connected but returned nothing.");
    return render(r.data);
  };

  // ---------- Pieces ----------
  const skRows = (n, cols) => Array.from({ length: n }, () => `<tr class="sk-row">${Array.from({ length: cols }, () => `<td><div class="skeleton" style="width:${50 + Math.random() * 40}%"></div></td>`).join("")}</tr>`).join("");
  const wlTable = (rows, demo) => `<div class="table-wrap"><table>
      <caption class="sr-only">Watchlist${demo ? " — sample data" : ""}</caption>
      <thead><tr><th scope="col">Symbol</th><th scope="col">Market</th><th scope="col" class="r">${demo ? "Sample price" : "Last price"}</th><th scope="col" class="r">24h</th><th scope="col" class="r">Volume</th></tr></thead>
      <tbody>${rows || skRows(5, 5)}</tbody></table></div>`;
  const prevPx = new Map();
  const wlRows = (data) => data.map((d) => {
    const key = d.symbol + d.market, prev = prevPx.get(key); prevPx.set(key, d.last);
    const flash = prev != null && prev !== d.last ? (d.last > prev ? "flash-up" : "flash-down") : "";
    return `<tr class="${flash}"><th scope="row" style="font-weight:600">${TA.esc(d.symbol)}</th><td><span class="badge">${d.market}</span></td><td class="r num">${TA.fmtPrice(d.last)}${d.priceLabel ? ` <span class="muted" style="font-size:.7rem" title="${d.priceLabel} from ${TA.esc(d.source)}">mid</span>` : ""}</td><td class="r">${TA.chg(d.change24h)}</td><td class="r num" title="24h quote volume (USDT)">${TA.fmtCompact(d.volume)}</td></tr>`;
  }).join("");
  const srcLine = (r) => r.source === "demo"
    ? `<p class="demo-stamp" style="margin:10px 0 0">${TA.icon("flask", "icon-sm")}Sample fixture — not market data</p>`
    : `<p class="muted" style="font-size:.78rem;margin:10px 0 0">Source: ${[...new Set(r.data.map((d) => d.source))].join(" & ")} · last price &amp; 24h stats · fetched ${ageHtml(r.fetchedAt)} · refreshes every ${C.watchlistRefreshSeconds}s</p>`;
  /** Render a watchlist into host and keep it refreshed (REST polling, paused while the tab is hidden). */
  async function mountWatchlist(host, onData) {
    const load = async () => {
      const r = await TA.MarketData.getWatchlist({ demo: store.demo });
      if (!host.isConnected) return;
      host.innerHTML = fromResult(r, "Watchlist data", (d) => wlTable(wlRows(d), r.source === "demo") + srcLine(r));
      onData && onData(r);
      return r;
    };
    const r = await load();
    if (r && r.source !== "demo" && r.status !== "disconnected") every(C.watchlistRefreshSeconds * 1000, load);
  }

  const chartSymbols = () => store.demo ? [{ symbol: "SAMPLE/USDT", market: "Futures" }] : C.watchlist;
  const chartControls = () => `
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
      <label class="sr-only" for="symSel">Symbol</label>
      <select id="symSel" class="sel" data-sym>${chartSymbols().map((w, i) => `<option value="${i}" ${i === ui.sym ? "selected" : ""}>${w.symbol} · ${w.market}</option>`).join("")}</select>
      <div class="seg" role="group" aria-label="Timeframe">${["1m", "15m", "1H", "4H", "1D"].map((t) => `<button type="button" data-tf="${t}" aria-pressed="${ui.tf === t}">${t}</button>`).join("")}</div>
      <div class="chips" role="group" aria-label="Indicators">
        <button type="button" class="chip" data-ind="ema" aria-pressed="${ui.ema}"><span class="term" data-tip="Exponential moving average — a trend line weighted toward recent prices." tabindex="-1">EMA 20</span></button>
        <button type="button" class="chip" data-ind="volume" aria-pressed="${ui.volume}">Volume</button>
        ${[["sma50", "SMA 50", "Simple average of the last 50 closes."], ["bb", "Bollinger", "20-period average ± 2 standard deviations."], ["vwap", "VWAP", "Volume-weighted average price since 00:00 UTC."],
           ["st", "Supertrend", "ATR-based trailing line; flips when price closes through it."], ["psar", "SAR", "Parabolic SAR dots: a trailing stop-style trend marker."],
           ["ichi", "Ichimoku cloud", "Area between Ichimoku spans A and B (no look-ahead)."], ["pat", "Patterns", "Markers for candlestick patterns: context, not predictions."],
           ["smc", "SMC", "Order blocks, fair value gaps, BOS/CHOCH levels and resting liquidity (algorithmic interpretations)."]]
          .map(([k, label, tip]) => `<button type="button" class="chip" data-ind="${k}" aria-pressed="${ui[k]}" title="${tip}">${label}</button>`).join("")}
      </div>
    </div>`;

  const statusLabel = { connecting: "Connecting…", live: "Live", reconnecting: "Reconnecting…", stale: "Stale — reconnecting", closed: "Closed", snapshot: "Snapshot", sample: "Sample" };

  async function loadChart(host) {
    if (host._handles) host._handles.forEach((h) => { h && h.close(); live.delete(h); });
    host._handles = []; host._redraw = null;
    const token = (host._token = (host._token || 0) + 1);   // newer loadChart calls win
    const current = () => host.isConnected && host._token === token;
    const area = host.querySelector(".chart-area"), meta = host.querySelector(".chart-meta"), prem = host.querySelector(".prem");
    const syms = chartSymbols(); if (ui.sym >= syms.length) ui.sym = 0;
    const w = syms[ui.sym];
    host.querySelector(".chart-title").textContent = `· ${w.symbol} · ${w.market}`;
    area.innerHTML = `<div class="skeleton" style="position:absolute;inset:12px"></div>`;
    meta.innerHTML = ""; prem.innerHTML = "";
    const r = await TA.MarketData.getCandles(w.symbol, w.market, ui.tf, { demo: store.demo });
    if (!current()) return;
    if (r.status !== "ok") { area.innerHTML = fromResult(r, "Chart data"); return; }

    let cs = r.data.slice(-150), lastMsg = r.fetchedAt, status = r.source === "demo" ? "sample" : "snapshot", raf = 0;
    const VIEW = 90;
    let lastA = null;
    const draw = () => {
      const a = (lastA = analyse(cs, ui.tf)), off = Math.max(0, cs.length - VIEW), cut = (arr) => arr.slice(off);
      const overlays = [], bands = [], dots = [];
      if (ui.sma50) overlays.push({ values: cut(a.sma50), color: "var(--teal)", label: "SMA 50" });
      if (ui.bb) { bands.push({ upper: cut(a.bb.upper), lower: cut(a.bb.lower), color: "var(--accent)", opacity: 0.07 }); overlays.push({ values: cut(a.bb.upper), color: "var(--tx-3)", width: 1, label: "Bollinger upper" }, { values: cut(a.bb.lower), color: "var(--tx-3)", width: 1, label: "Bollinger lower" }); }
      if (ui.vwap) overlays.push({ values: cut(a.vwap), color: "#C59BFF", dash: "4 3", label: "VWAP" });
      if (ui.st) {
        const line = cut(a.st.supertrend), dir = cut(a.st.direction);
        overlays.push({ values: line.map((v, i) => (dir[i] === 1 ? v : null)), color: "var(--up)", width: 1.6, label: "Supertrend (up)" }, { values: line.map((v, i) => (dir[i] === -1 ? v : null)), color: "var(--down)", width: 1.6, label: "Supertrend (down)" });
      }
      if (ui.psar) dots.push({ values: cut(a.psar), color: "var(--tx-2)" });
      if (ui.ichi) bands.push({ upper: cut(a.ichi.span_a), lower: cut(a.ichi.span_b), color: "var(--teal)", opacity: 0.12 });
      const boxes = [], hlines = [];
      if (ui.smc) {
        const S = a.smc, last = VIEW - 1, rel = (i) => i - off;
        S.order_blocks.filter((b) => b.status !== "broken" && b.created_index >= off).slice(-6).forEach((b) =>
          boxes.push({ i0: Math.max(0, rel(b.index)), i1: last, lo: b.low, hi: b.high, color: b.direction === "bullish" ? "var(--up)" : "var(--down)", label: `${b.direction} order block (${b.status})` }));
        S.fvgs.filter((g) => g.status !== "filled" && g.index >= off).slice(-6).forEach((g) =>
          boxes.push({ i0: rel(g.index), i1: last, lo: g.low, hi: g.high, color: "var(--accent)", label: `${g.direction} fair value gap (${g.status})` }));
        S.structure.filter((e) => e.index >= off).slice(-6).forEach((e) =>
          hlines.push({ i0: Math.max(0, rel(e.swing_index)), i1: rel(e.index), y: e.level, color: e.direction === "bullish" ? "var(--up)" : "var(--down)", text: e.type, label: `${e.type} ${e.direction}` }));
        S.liquidity.levels.filter((x) => x.status === "resting" && x.index >= off).slice(-6).forEach((x) =>
          hlines.push({ i0: rel(x.index), i1: last, y: x.level, color: "var(--tx-3)", dash: "2 3", text: x.side + (x.equal ? " (equal)" : ""), label: `${x.side} resting liquidity` }));
        if (S.premium_discount) hlines.push({ i0: 0, i1: last, y: S.premium_discount.equilibrium, color: "var(--teal)", dash: "6 4", text: "EQ", label: "Equilibrium of the dealing range" });
      }
      const markers = ui.pat ? a.patterns.filter((p) => p.index >= off).map((p) => ({ index: p.index - off, bias: p.bias, label: `${p.pattern} (${p.bias})` })) : [];
      area.innerHTML = TA.candleChart(cs.slice(-VIEW), { w: 900, h: 340, ema: ui.ema, volume: ui.volume, overlays, bands, dots, markers, boxes, hlines });
      if (readings) renderReadings();
    };
    const readings = host.querySelector(".readings");
    let rTimer = 0;
    const renderReadings = () => {
      if (rTimer) return;
      rTimer = setTimeout(() => { rTimer = 0; if (current() && lastA) readings.innerHTML = readingsHtml(lastA, cs, w, r.source === "demo"); }, readings.innerHTML ? 1000 : 0);
    };
    const renderMeta = () => {
      const last = cs[cs.length - 1], dir = last.c >= last.o;
      const st = status === "live" ? `<span class="badge badge-info"><span class="dot dot-live"></span>${statusLabel[status]}</span>`
        : status === "sample" ? `<span class="badge badge-demo">${TA.icon("flask", "icon-sm")}Sample</span>`
        : `<span class="badge ${status === "stale" || status === "reconnecting" ? "badge-short" : ""}">${statusLabel[status] || status}</span>`;
      meta.innerHTML = `<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:.84rem">
        ${st}<span><span class="muted">${w.market === "Futures" ? "Last" : "Price"}</span> <b class="num ${dir ? "up" : "down"}">${TA.fmtPrice(last.c)}</b></span>
        <span class="muted">Candle opened ${TA.fmtTime(last.t)}</span>
        <span class="muted">Source: ${TA.esc(r.sourceName || "")}</span>
        <span class="muted">Updated ${ageHtml(lastMsg)}</span>
        ${r.meta && r.meta.gaps ? `<span class="down">${r.meta.gaps} missing candle(s) in range</span>` : ""}</div>`;
    };
    // rAF while visible; a slow timer when hidden (rAF pauses there) so status/freshness stay truthful
    const schedule = () => {
      if (raf) return;
      const run = () => { raf = 0; if (current()) { draw(); renderMeta(); } };
      raf = document.hidden ? setTimeout(run, 1000) : requestAnimationFrame(run);
    };
    const merge = (list) => {
      const byT = new Map(cs.map((c) => [c.t, c]));
      list.forEach((c) => byT.set(c.t, c));
      cs = [...byT.values()].sort((a, b) => a.t - b.t).slice(-150);
    };
    draw(); renderMeta();
    host._redraw = () => { if (current()) draw(); };

    // Live candle updates (browser provider only). After a reconnect, reconcile recent candles over REST.
    const h = TA.MarketData.streamCandles(w.symbol, w.market, ui.tf, (c) => {
      const last = cs[cs.length - 1];
      if (c.t < last.t) return;                       // ignore out-of-order updates
      merge([c]); lastMsg = Date.now(); schedule();
    }, async (st, info) => {
      status = st; schedule();
      if (st === "live" && info && info.reconnected) {
        const rr = await TA.MarketData.getCandles(w.symbol, w.market, ui.tf, { limit: 20 });
        if (rr.status === "ok" && current()) { merge(rr.data); lastMsg = Date.now(); schedule(); }
      }
    }, { demo: store.demo });
    host._handles.push(track(h));

    // Futures: last vs mark vs index, funding
    if (w.market === "Futures" && !store.demo) {
      const renderPrem = (p, ts) => {
        const cell = (k, v, tip) => `<div class="result"><small>${tip ? `<span class="term" tabindex="0" data-tip="${tip}">${k}</span>` : k}</small><div>${v}</div></div>`;
        prem.innerHTML = `<div class="result-grid" style="grid-template-columns:repeat(auto-fit,minmax(125px,1fr));margin-top:12px">
          ${cell("Last price", TA.fmtPrice(cs[cs.length - 1].c), "Price of the most recent trade on this contract.")}
          ${cell("Mark price", TA.fmtPrice(p.mark), "Price Binance uses for unrealised P&L and liquidations.")}
          ${p.indexLabel === "Oracle price" ? cell("Oracle price", TA.fmtPrice(p.index), "Hyperliquid's reference price from several exchanges (closest equivalent to an index price).") : cell("Index price", TA.fmtPrice(p.index), "Average spot price across several exchanges.")}
          ${cell("Funding rate", `<span class="${p.fundingRate >= 0 ? "up" : "down"}">${(p.fundingRate * 100).toFixed(4)}%</span>`, `Periodic payment between longs and shorts${p.fundingInterval ? `, settled every ${p.fundingInterval}` : ""}. Positive: longs pay shorts.`)}
          ${cell("Next funding", TA.fmtTime(p.nextFundingTime))}
        </div><p class="muted" style="font-size:.78rem;margin:8px 0 0">Source: ${TA.esc(p.source)} · mark/index/funding updated ${ageHtml(ts)}</p>
        ${TA.MarketData.usingFuturesFallback() ? `<div class="integration" style="margin-top:10px">${TA.icon("info", "icon-sm")}<span>Binance Futures isn't reachable from your region, so Futures data comes from Hyperliquid perpetuals (USDC-settled). Prices can differ slightly from Binance.</span></div>` : ""}`;
      };
      TA.MarketData.getPremium(w.symbol).then((pr) => {
        if (!current()) return;
        if (pr.status === "ok") renderPrem(pr.data, pr.fetchedAt);
        else if (pr.status === "error") prem.innerHTML = `<p class="down" style="font-size:.84rem;margin-top:12px">${TA.icon("alert", "icon-sm")} Couldn't load mark/index/funding: ${TA.esc(pr.error)}</p>`;
      });
      let pRaf = 0, pLast = null;
      host._handles.push(track(TA.MarketData.streamPremium(w.symbol, (p) => {
        pLast = p;
        if (!pRaf) pRaf = setTimeout(() => { pRaf = 0; if (current() && pLast) renderPrem(pLast, Date.now()); }, 1000);
      }, () => {})));
    }
  }
  function chartPanel(title = "Primary chart", { withReadings = false } = {}) {
    return `<section class="card panel" data-chart>
      <div class="panel-head"><h2>${TA.icon("candles")}${title} <span class="muted chart-title" style="font-weight:500;font-size:.85rem"></span></h2>${chartControls()}</div>
      <div class="chart-area"></div><div class="chart-meta" style="margin-top:10px"></div><div class="prem"></div></section>
      ${withReadings ? `<section class="card panel readings" aria-live="off"></section>` : ""}`;
  }

  // ---------- Technical analysis (TA.Analysis twin of the backend library) ----------
  const INTERVAL_MS = { "1m": 60e3, "5m": 300e3, "15m": 900e3, "1H": 3600e3, "4H": 14400e3, "1D": 86400e3 };
  function analyse(cs, tf) {
    const A = TA.Analysis, t = cs.map((c) => c.t), o = cs.map((c) => c.o), h = cs.map((c) => c.h), l = cs.map((c) => c.l), c = cs.map((x) => x.c), v = cs.map((x) => x.v);
    return {
      t, o, h, l, c, v,
      sma20: A.sma(c, 20), sma50: A.sma(c, 50), ema20: A.ema(c, 20), wma20: A.wma(c, 20), vwma20: A.vwma(c, v, 20),
      rsi: A.rsi(c), macd: A.macd(c), stoch: A.stochastic(h, l, c), cci: A.cci(h, l, c), mfi: A.mfi(h, l, c, v),
      atr: A.atr(h, l, c), bb: A.bollinger(c), kc: A.keltner(h, l, c), adx: A.adx(h, l, c), st: A.supertrend(h, l, c),
      ichi: A.ichimoku(h, l, c), psar: A.parabolicSar(h, l), obv: A.obv(c, v), vwap: A.vwap(t, h, l, c, v),
      vp: A.volumeProfile(h, l, c, v), fib: A.fibonacci(h, l), piv: A.pivots(t, h, l, c, INTERVAL_MS[tf]),
      patterns: A.detectCandlestickPatterns(o, h, l, c), formations: A.doubleTopsBottoms(h, l, c),
      smc: TA.SMC.analyzeSmc(o, h, l, c)
    };
  }
  const lastOf = (arr) => (arr && arr.length ? arr[arr.length - 1] : null);
  const fmtN = (v, d = 2) => (v == null || !Number.isFinite(v) ? "—" : Math.abs(v) >= 1e6 ? TA.fmtCompact(v) : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }));
  const term = (label, tip) => `<span class="term" tabindex="0" data-tip="${tip}">${label}</span>`;

  /** Plain-language, descriptive readings. No buy/sell language — these describe the chart, they don't predict it. */
  function readingsHtml(a, cs, w, demo) {
    const px = lastOf(a.c), P = TA.fmtPrice;
    const rsi = lastOf(a.rsi), adx = lastOf(a.adx.adx), pdi = lastOf(a.adx.plus_di), mdi = lastOf(a.adx.minus_di), stK = lastOf(a.stoch.k), stD = lastOf(a.stoch.d);
    const m = lastOf(a.macd.macd), ms = lastOf(a.macd.signal), mh = lastOf(a.macd.histogram), stDir = lastOf(a.st.direction);
    const pos = (v, ref) => (v == null || ref == null ? "" : px > ref ? "price above" : px < ref ? "price below" : "price at");
    const zone = (v, lo, hi, loTxt, hiTxt) => (v == null ? "warming up" : v >= hi ? hiTxt : v <= lo ? loTxt : "middle range");
    const row = (name, tip, value, note) => `<tr><th scope="row">${term(name, tip)}</th><td class="r num">${value}</td><td class="muted">${note}</td></tr>`;
    const group = (title, rows) => `<h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:18px 0 8px">${title}</h3><div class="table-wrap"><table><tbody>${rows.join("")}</tbody></table></div>`;
    const recent = a.patterns.filter((p) => p.index >= cs.length - 30).slice(-12).reverse();
    const biasBadge = (b) => b === "bullish" ? `<span class="badge badge-long">${TA.icon("arrowUp", "icon-sm")}Bullish context</span>` : b === "bearish" ? `<span class="badge badge-short">${TA.icon("arrowDown", "icon-sm")}Bearish context</span>` : `<span class="badge badge-none">${TA.icon("minus", "icon-sm")}Neutral</span>`;
    const fib = a.fib, piv = a.piv, vp = a.vp;
    return `<div class="panel-head" style="margin-bottom:4px"><h2>${TA.icon("gauge")}Indicator readings <span class="muted" style="font-weight:500;font-size:.85rem">· ${w.symbol} · ${ui.tf} · last ${cs.length} candles</span></h2>${demo ? '<span class="badge badge-demo">Sample data</span>' : ""}</div>
      <p class="muted" style="font-size:.8rem;margin:0">Calculated in your browser from the candles above. They describe past price action. They are context, not predictions or advice.</p>
      ${group("Trend", [
        row("SMA 20 / 50", "Simple moving averages of the last 20 and 50 closes.", `${fmtN(lastOf(a.sma20))} / ${fmtN(lastOf(a.sma50))}`, `${pos(px, lastOf(a.sma50))} SMA 50`),
        row("EMA 20", "Exponential moving average, weighted toward recent closes.", fmtN(lastOf(a.ema20)), pos(px, lastOf(a.ema20)) + " EMA 20"),
        row("WMA 20 / VWMA 20", "Linearly weighted and volume-weighted 20-period averages.", `${fmtN(lastOf(a.wma20))} / ${fmtN(lastOf(a.vwma20))}`, ""),
        row("ADX 14 (+DI / −DI)", "ADX measures trend strength (not direction). Above ~25 is often read as a trending market; +DI vs −DI shows which side has been stronger.", `${fmtN(adx, 1)} (${fmtN(pdi, 1)} / ${fmtN(mdi, 1)})`, adx == null ? "warming up" : `${adx >= 25 ? "strong" : adx >= 20 ? "moderate" : "weak"} trend strength · ${pdi > mdi ? "+DI above −DI" : "−DI above +DI"}`),
        row("Supertrend (10, 3)", "ATR-based trailing line; its side flips when a close crosses it.", fmtN(lastOf(a.st.supertrend)), stDir == null ? "warming up" : stDir === 1 ? "line below price (up state)" : "line above price (down state)"),
        row("Parabolic SAR", "Trailing dots that switch side when price crosses them.", fmtN(lastOf(a.psar)), lastOf(a.psar) == null ? "" : lastOf(a.psar) < px ? "below price" : "above price"),
        row("Ichimoku (tenkan / kijun)", "Midpoints of the 9- and 26-bar ranges.", `${fmtN(lastOf(a.ichi.tenkan))} / ${fmtN(lastOf(a.ichi.kijun))}`, (() => { const sa = lastOf(a.ichi.span_a), sb = lastOf(a.ichi.span_b); if (sa == null || sb == null) return "cloud warming up (needs 78 bars)"; return px > Math.max(sa, sb) ? "price above the cloud" : px < Math.min(sa, sb) ? "price below the cloud" : "price inside the cloud"; })())
      ])}
      ${group("Momentum", [
        row("RSI 14", "Relative Strength Index (0–100). Above 70 and below 30 are commonly called overbought / oversold zones.", fmtN(rsi, 1), zone(rsi, 30, 70, "at/below 30 (oversold zone)", "at/above 70 (overbought zone)")),
        row("MACD (12, 26, 9)", "EMA12 − EMA26, its 9-period signal line, and the histogram (difference).", `${fmtN(m, 4)} / ${fmtN(ms, 4)}`, mh == null ? "warming up" : `histogram ${mh >= 0 ? "positive" : "negative"} (${fmtN(mh, 4)})`),
        row("Stochastic (14, 3, 3)", "Where the close sits in the 14-bar range (0–100), smoothed.", `${fmtN(stK, 1)} / ${fmtN(stD, 1)}`, zone(stK, 20, 80, "at/below 20", "at/above 80")),
        row("CCI 20", "Distance of typical price from its average, in units of mean deviation.", fmtN(lastOf(a.cci), 1), zone(lastOf(a.cci), -100, 100, "below −100", "above +100")),
        row("MFI 14", "Volume-weighted RSI using typical price.", fmtN(lastOf(a.mfi), 1), zone(lastOf(a.mfi), 20, 80, "at/below 20", "at/above 80"))
      ])}
      ${group("Volatility", [
        row("ATR 14", "Average True Range: typical bar size including gaps, in price units.", fmtN(lastOf(a.atr), 4), lastOf(a.atr) == null ? "" : `${((lastOf(a.atr) / px) * 100).toFixed(2)}% of price`),
        row("Bollinger (20, 2)", "20-period SMA ± 2 standard deviations.", `${fmtN(lastOf(a.bb.lower))} – ${fmtN(lastOf(a.bb.upper))}`, lastOf(a.bb.upper) == null ? "" : px > lastOf(a.bb.upper) ? "close above upper band" : px < lastOf(a.bb.lower) ? "close below lower band" : "inside the bands"),
        row("Keltner (20, 2, ATR 10)", "EMA 20 ± 2 × ATR 10.", `${fmtN(lastOf(a.kc.lower))} – ${fmtN(lastOf(a.kc.upper))}`, "")
      ])}
      ${group("Volume", [
        row("VWAP (UTC day)", "Volume-weighted average price since 00:00 UTC today.", fmtN(lastOf(a.vwap)), pos(px, lastOf(a.vwap)) + " VWAP"),
        row("OBV", "On-Balance Volume: running total of volume, added on up closes and subtracted on down closes.", fmtN(lastOf(a.obv), 0), "trend of this line matters more than its level"),
        row("Volume profile POC", "Price level with the most traded volume in view (24 bins); value area holds 70% of volume.", fmtN(vp.poc), vp.poc == null ? "" : `value area ${fmtN(vp.value_area_low)} – ${fmtN(vp.value_area_high)}`)
      ])}
      ${group("Levels", [
        row("Pivots (classic)", `Floor pivots from the ${piv ? piv.basis : "previous period"}.`, piv ? fmtN(piv.p) : "—", piv ? `R1 ${fmtN(piv.r1)} · S1 ${fmtN(piv.s1)} · R2 ${fmtN(piv.r2)} · S2 ${fmtN(piv.s2)}` : "needs the previous UTC day in view"),
        row("Fibonacci retracement", "Ratios between the highest high and lowest low in view.", fib ? `${fmtN(fib.swing_low)} – ${fmtN(fib.swing_high)}` : "—", fib ? `${fib.direction} move · 38.2% ${fmtN(fib.levels["0.382"])} · 50% ${fmtN(fib.levels["0.5"])} · 61.8% ${fmtN(fib.levels["0.618"])}` : "")
      ])}
      ${(() => {
        const S = a.smc, ev = S.structure[S.structure.length - 1], pd = S.premium_discount;
        const ob = S.order_blocks.filter((b) => b.status !== "broken"), fv = S.fvgs.filter((g) => g.status !== "filled");
        const bsl = S.liquidity.levels.filter((x) => x.side === "BSL" && x.status === "resting" && x.level > px).sort((p, q) => p.level - q.level)[0];
        const ssl = S.liquidity.levels.filter((x) => x.side === "SSL" && x.status === "resting" && x.level < px).sort((p, q) => q.level - p.level)[0];
        const sw = S.liquidity.sweeps.filter((x) => x.event_index >= cs.length - 10);
        return group("Smart Money Concepts", [
          row("Structure", "BOS = break of structure (continuation); CHOCH = change of character (reversal). Based on closes through confirmed swing points.", ev ? `${ev.type} ${ev.direction}` : "—", ev ? `close through ${fmtN(ev.level)} · ${TA.fmtTime(a.t[ev.index])}` : "no structure break in view"),
          row("Order blocks", "Last opposite candle before a structure break. Fresh = not revisited; mitigated = price returned into it.", `${ob.length} active`, ob.slice(-2).map((b) => `${b.direction} ${fmtN(b.low)}–${fmtN(b.high)} (${b.status})`).join(" · ") || "none"),
          row("Fair value gaps", "Three-candle gaps where price moved fast, at least 0.1 ATR wide.", `${fv.length} unfilled`, fv.slice(-2).map((g) => `${g.direction} ${fmtN(g.low)}–${fmtN(g.high)} (${g.status})`).join(" · ") || "none"),
          row("Liquidity", "Resting liquidity = unbroken swing highs (BSL) and lows (SSL). A sweep wicks through and closes back.", `${bsl ? fmtN(bsl.level) : "—"} / ${ssl ? fmtN(ssl.level) : "—"}`, `nearest BSL above / SSL below${sw.length ? ` · ${sw.length} sweep(s) in last 10 candles` : ""}`),
          row("Premium / discount", "Position in the range between the latest swing high and swing low. Above the midpoint = premium.", pd ? pd.zone : "—", pd ? `equilibrium ${fmtN(pd.equilibrium)} · range ${fmtN(pd.range_low)}–${fmtN(pd.range_high)}` : "needs swing high and low")
        ]) + `<p class="muted" style="font-size:.76rem;margin:6px 0 0">SMC readings are algorithmic interpretations of price action. They don't show what institutions are doing.</p>`;
      })()}
      <h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:18px 0 8px">Candlestick patterns · last 30 candles</h3>
      ${recent.length ? `<ul class="list-signals" style="list-style:none;margin:0;padding:0">${recent.map((p) => `<li class="sig-row" style="cursor:default">${biasBadge(p.bias)}<span><b>${p.pattern}</b><br/><span class="muted" style="font-size:.8rem">${p.candles.length} candle${p.candles.length > 1 ? "s" : ""} · ${TA.fmtTime(a.t[p.index])}</span></span><span class="muted" style="font-size:.78rem">${((n) => (n === 0 ? "current candle" : n === 1 ? "1 bar ago" : `${n} bars ago`))(cs.length - 1 - p.index)}</span></li>`).join("")}</ul>`
        : `<p class="muted" style="font-size:.86rem">No patterns in the last 30 candles.</p>`}
      <h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:18px 0 8px">Chart formations</h3>
      ${a.formations.length ? `<ul style="margin:0;padding-left:18px;font-size:.88rem;color:var(--tx-2)">${a.formations.slice(-5).map((f) => `<li>${f.formation} · neckline ${fmtN(f.neckline)} · <b>${f.status}</b> · peaks ${TA.fmtTime(a.t[f.points[0]])} and ${TA.fmtTime(a.t[f.points[2]])}</li>`).join("")}</ul>`
        : `<p class="muted" style="font-size:.86rem">No double tops or bottoms in view.</p>`}
      <p class="muted" style="font-size:.76rem;margin:14px 0 0">The current candle is still forming, so its patterns and readings can change until it closes. Formulas: see the project README and <code>backend/app/analysis</code>.</p>`;
  }

  // ---------- Views ----------
  // Pro features open with an active trial or paid plan. Their data comes from public exchange APIs in the browser,
  // so this is a product gate rather than a security boundary.
  async function proGate(el, title, blurb) {
    if (store.demo || !TA.Auth.available()) return true;
    const u = (await TA.Signals.getUsage()).data || {};
    if (u.pro) return true;
    if (!el.isConnected) return false;
    const signedOut = !!u.signedOut;
    try { sessionStorage.setItem("ta-after-auth", location.hash); } catch {}
    el.innerHTML = `<section class="card panel" style="text-align:center;padding:36px 22px">
      <span class="badge" style="margin:0 auto 12px">TRADE-AI Pro</span>
      <h2 style="font-size:1.4rem;margin:0 0 8px">${TA.esc(title)}</h2>
      <p class="muted" style="max-width:520px;margin:0 auto 18px">${TA.esc(blurb)}</p>
      <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
        ${signedOut ? `<a class="btn btn-primary" href="#/account">Start ${C.pricing.trialDays}-day free trial</a><a class="btn" href="#/account">Sign in</a>`
          : `<a class="btn btn-primary" href="#/billing">Upgrade to Pro · $${C.pricing.monthlyPrice}/month</a>`}</div>
      <p class="muted" style="font-size:.82rem;margin:16px 0 0">${signedOut ? "No card needed for the trial." : "Your free trial has ended."} Dashboard, charts, signals, history and risk tools stay free.</p></section>`;
    return false;
  }

  const views = {
    async dashboard(el) {
      el.innerHTML = `
        <div class="status-row">
          <div class="card stat"><small>Market status</small><strong id="mkStatus">${store.demo ? "Sample" : TA.MarketData.isConfigured() ? "Open 24/7" : "Unknown"}</strong><p class="muted">${store.demo ? "Preview fixture" : TA.MarketData.isConfigured() ? "Crypto trades continuously" : "Needs data feed"}</p></div>
          <div class="card stat"><small>Data connection</small><strong>${store.demo ? `<span class="dot" style="color:var(--accent)"></span>Sample` : TA.MarketData.isConfigured() ? `<span class="dot dot-live" style="color:var(--teal)"></span>Live` : `${TA.icon("wifiOff", "icon-sm")}Offline`}</strong><p class="muted">${TA.esc(TA.MarketData.describeSource(store.demo))}</p></div>
          <div class="card stat"><small>Data freshness</small><strong id="fresh">—</strong><p class="muted">Watchlist · stale after ${C.api.staleAfterSeconds}s</p></div>
          <div class="card stat"><small>Your plan</small><strong id="usageTxt"><span class="skeleton" style="width:60px;display:inline-block">&nbsp;</span></strong><p class="muted" id="usageSub"></p></div>
        </div>
        <div class="grid-dash">
          <div class="span-8">${chartPanel()}</div>
          <section class="card panel span-4"><div class="panel-head"><h2>${TA.icon("zap")}Recent signals</h2><a class="btn btn-ghost btn-sm" href="#/signals">View all</a></div><div id="recent" class="list-signals">${Array.from({ length: 3 }, () => '<div class="skeleton" style="height:58px;border-radius:12px"></div>').join("")}</div></section>
          <section class="card panel span-12"><div class="panel-head"><h2>${TA.icon("star")}Watchlist</h2></div><div id="wl">${wlTable(null)}</div></section>
        </div>`;
      loadChart(el.querySelector("[data-chart]"));

      mountWatchlist($("#wl", el), (wl) => { $("#fresh", el).innerHTML = wl.fetchedAt ? ageHtml(wl.fetchedAt) : "No data"; });
      const [sig, use] = await Promise.all([TA.Signals.getRecent({ demo: store.demo }), TA.Signals.getUsage({ demo: store.demo })]);
      if (!el.isConnected) return;
      if (sig.status === "ok") lastSignals = sig.data;
      $("#recent", el).innerHTML = sig.status === "disconnected"
        ? state("off", "No signal feed", "Signals appear here once an approved signal backend is connected.", demoBtn)
        : fromResult(sig, "Signals", (d) => d.map((s) => `<button class="sig-row" data-sig="${s.id}">${TA.dirBadge(s.direction)}<span><b>${TA.esc(s.symbol)}</b><br/><span class="muted" style="font-size:.8rem">${s.timeframe} · ${TA.lifeLabel[s.lifecycle]}</span></span><span class="muted" style="font-size:.78rem">${TA.ago(s.createdAt)}</span></button>`).join("") + (sig.source === "demo" ? `<p class="demo-stamp" style="margin:4px 0 0">${TA.icon("flask", "icon-sm")}Illustrative examples</p>` : ""));
      const u = use.data || {};
      $("#usageTxt", el).innerHTML = u.signedOut ? `<a href="#/account" style="font-size:1rem">Start free trial</a>`
        : u.plan && u.plan !== "trial" ? "Pro" : u.pro ? "Pro trial" : "Free";
      $("#usageSub", el).textContent = u.signedOut ? `${C.pricing.trialDays} days of Pro, no card needed`
        : u.plan && u.plan !== "trial" ? "All analysis tools" : u.pro ? `${u.trial_days_left} day${u.trial_days_left === 1 ? "" : "s"} left` : "Upgrade for scanner, futures & SMC";
    },

    async markets(el) {
      el.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("globe")}Market overview</h2><span class="muted" style="font-size:.85rem">Spot &amp; Futures</span></div><div id="m">${wlTable(null)}</div></section>`;
      mountWatchlist($("#m", el));
    },

    async watchlist(el) {
      el.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("star")}Your watchlist</h2><button class="btn btn-sm" aria-disabled="true" title="Requires accounts">${TA.icon("plus", "icon-sm")}Add symbol</button></div>
        <div class="integration" style="margin-bottom:14px">${TA.icon("info", "icon-sm")}<span>Saving symbols needs accounts and a backend. Adding is disabled until then.</span></div><div id="w">${wlTable(null)}</div></section>`;
      mountWatchlist($("#w", el));
    },

    async signals(el) {
      let filter = "ALL";
      el.innerHTML = strategyNotice() + `<div class="panel-head" style="margin:0"><div class="seg" role="group" aria-label="Filter by direction">${["ALL", "LONG", "SHORT", "NO TRADE"].map((f) => `<button data-f="${f}" aria-pressed="${f === filter}">${f === "ALL" ? "All" : f[0] + f.slice(1).toLowerCase()}</button>`).join("")}</div></div>
        <div id="sg" class="module-grid">${Array.from({ length: 3 }, () => '<div class="skeleton" style="height:320px;border-radius:18px"></div>').join("")}</div>`;
      const r = await TA.Signals.getRecent({ demo: store.demo });
      if (!el.isConnected) return;
      if (r.status === "ok") lastSignals = r.data;
      const draw = () => {
        const host = $("#sg", el);
        if (r.status !== "ok") { host.style.display = "block"; host.innerHTML = `<div class="card">${r.status === "disconnected" ? state("off", "No signal feed connected", "Signals are produced by the TRADE-AI server (strategy smc_trend_pullback v1.0.0) and stored with their evidence. They'll appear here once the backend is hosted and <code>api.backendBaseUrl</code> is set.", demoBtn) : fromResult(r, "Signals")}</div>`; return; }
        const list = r.data.filter((s) => filter === "ALL" || s.direction === filter);
        host.innerHTML = list.length ? list.map((s, i) => `<div class="reveal" style="--d:${i * 60}ms" data-sig="${s.id}" role="button" tabindex="0" aria-label="Open ${TA.esc(s.symbol)} details">${TA.signalCard(s)}</div>`).join("") : `<div class="card" style="grid-column:1/-1">${state("empty", "Nothing matches this filter", "Try another direction.")}</div>`;
        TA.initReveal(host);
      };
      el.querySelectorAll("[data-f]").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.f; el.querySelectorAll("[data-f]").forEach((x) => x.setAttribute("aria-pressed", x === b)); draw(); }));
      draw();
    },

    chart(el) { el.innerHTML = `<div class="chart-wrap">${chartPanel("Advanced chart", { withReadings: true })}</div>`; loadChart(el.querySelector(".chart-wrap")); },

    async history(el) {
      el.innerHTML = `<div class="panel-head" style="margin:0"><div class="seg" role="tablist" aria-label="Result type">
          <button role="tab" data-kind="prospective" aria-selected="true">Live signals (prospective)</button>
          <button role="tab" data-kind="backtest" aria-selected="false">Backtests</button>
          <button role="tab" data-kind="paper" aria-selected="false">Paper</button></div></div>
        ${strategyNotice()}<div id="perf"></div>
        <section class="card panel"><h2 style="font-size:1rem">${TA.icon("info")}How results are measured</h2>
          <ul style="margin:0;padding-left:18px;font-size:.88rem;color:var(--tx-2);display:grid;gap:4px">
            <li><b>Live signals, backtests and paper trading are kept separate.</b> They are never added together.</li>
            <li>Fills assume the worse edge of the entry zone. One third exits at each target, and the rest at the stop or a time exit. Fees and slippage are included. If a stop and a target are touched in the same candle, the stop is assumed first unless 1-minute data shows otherwise.</li>
            <li>Backtests use only data available at each decision. They're split by date into development, validation and an untouched out-of-sample period, and they also run walk-forward tests.</li>
            <li>No accuracy rate is claimed. Win rates are always shown with the number of trades, and fewer than 30 trades is flagged as too few.</li>
          </ul></section>`;
      const host = $("#perf", el);
      const tabs = el.querySelectorAll("[data-kind]");
      tabs.forEach((b) => b.addEventListener("click", () => { tabs.forEach((x) => x.setAttribute("aria-selected", x === b)); show(b.dataset.kind); }));
      const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`), r2 = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}R`);
      const card = (k, v, tip) => `<div class="result"><small>${tip ? term(k, tip) : k}</small><div>${v}</div></div>`;
      const metricCards = (m) => `<div class="result-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
          ${card("Trades", m.trades)}${card("Win rate", m.trades ? `${pct(m.win_rate)} <span class="muted" style="font-size:.8rem">(${m.wins} of ${m.trades})</span>` : "—", "Share of trades with a positive net result. Always read it with the trade count.")}
          ${card("Profit factor", m.profit_factor == null ? "—" : m.profit_factor.toFixed(2), "Total won ÷ total lost, in R.")}
          ${card("Expectancy", r2(m.expectancy_r), "Average net result per trade, in multiples of the amount risked (R).")}
          ${card("Net P&L", m.net_pnl_pct == null ? "—" : `${m.net_pnl_pct >= 0 ? "+" : ""}${m.net_pnl_pct.toFixed(2)}%`, `Compounded, risking ${m.risk_per_trade_pct}% per trade, after fees and slippage.`)}
          ${card("Max drawdown", m.max_drawdown_pct == null ? "—" : `${m.max_drawdown_pct.toFixed(2)}%`, "Largest peak-to-trough fall of the equity curve.")}
          ${card("Avg win / loss", `${r2(m.avg_win_r)} / ${r2(m.avg_loss_r)}`)}${card("Worst losing streak", m.max_consecutive_losses ?? "—")}
        </div>${(m.warnings || []).map((w) => `<p class="down" style="font-size:.86rem;margin:10px 0 0">${TA.icon("alert", "icon-sm")} ${TA.esc(w)}</p>`).join("")}`;
      const curve = (pts) => {
        if (!pts || pts.length < 2) return "";
        const ys = pts.map((p) => p.equity), lo = Math.min(1, ...ys), hi = Math.max(1, ...ys), W = 800, H2 = 160;
        const y = (v) => 10 + ((hi - v) / (hi - lo || 1)) * (H2 - 20), x = (i) => (i / (pts.length - 1)) * W;
        return `<div class="chart-area" style="height:170px;margin-top:12px"><svg viewBox="0 0 ${W} ${H2}" preserveAspectRatio="none" role="img" aria-label="Equity curve"><line x1="0" x2="${W}" y1="${y(1)}" y2="${y(1)}" stroke="var(--tx-3)" stroke-dasharray="4 4"/><polyline points="${pts.map((p, i) => `${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="1.6"/></svg></div>`;
      };
      const breakdown = (title, g) => !g || !Object.keys(g).length ? "" : `<h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:16px 0 8px">${title}</h3><div class="table-wrap"><table><thead><tr><th>Group</th><th class="r">Trades</th><th class="r">Win rate</th><th class="r">Total</th><th class="r">Average</th></tr></thead><tbody>${Object.entries(g).map(([k, v]) => `<tr><td>${TA.esc(k)}</td><td class="r num">${v.trades}</td><td class="r num">${pct(v.win_rate)}</td><td class="r num">${r2(v.total_r)}</td><td class="r num">${r2(v.avg_r)}</td></tr>`).join("")}</tbody></table></div>`;
      const offline = () => state("off", "Results come from the TRADE-AI server", "Live signals are tracked and backtests are run on the server, so measured results appear here once the backend is hosted and <code>api.backendBaseUrl</code> is set. Nothing is estimated in the meantime.");

      async function show(kind) {
        host.innerHTML = `<div class="card panel"><div class="skeleton" style="height:120px"></div></div>`;
        if (kind === "paper") { host.innerHTML = `<section class="card">${state("soon", "Paper trading isn't available yet", "When it's added, paper results will be reported here on their own, separate from live signals and backtests.")}</section>`; return; }
        if (kind === "prospective") {
          const [p, hist] = await Promise.all([TA.Signals.getPerformance("prospective"), TA.Signals.getHistory()]);
          if (!host.isConnected) return;
          if (p.status !== "ok") { host.innerHTML = `<section class="card">${p.status === "disconnected" ? offline() : state("error", "Couldn't load results", TA.esc(p.error), retryBtn)}</section>`; return; }
          const d = p.data, m = d.metrics;
          host.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("database")}Live signals: measured results</h2><span class="badge badge-info">Prospective</span></div>
              <p class="muted" style="font-size:.84rem;margin:0 0 12px">${TA.esc(d.note)} ${d.open_or_unfilled} signal(s) still open or waiting for entry aren't counted.</p>
              ${metricCards(m)}${curve(m.equity_curve)}${breakdown("By side", m.by_side)}${breakdown("By exit", m.by_exit)}${breakdown("By month", m.by_month)}</section>
            <section class="card panel"><div class="panel-head"><h2>${TA.icon("history")}Signal log</h2><span class="muted" style="font-size:.82rem">${hist.status === "ok" ? `${hist.data.total} evaluations, including NO TRADE` : ""}</span></div>
              ${hist.status === "ok" && hist.data.items.length ? `<div class="table-wrap"><table><thead><tr><th>Time</th><th>Symbol</th><th>Result</th><th>Lifecycle</th><th class="r">Net result</th></tr></thead><tbody>${hist.data.items.map((x) => `<tr><td>${TA.fmtTime(x.generated_at)}</td><td>${TA.esc(x.symbol)} · ${x.timeframe}</td><td>${TA.dirBadge(x.side)}</td><td>${TA.lifeLabel[x.lifecycle] || x.lifecycle}</td><td class="r num">${x.outcome ? r2(x.outcome.net_r) : "—"}</td></tr>`).join("")}</tbody></table></div>` : state("empty", "No signals recorded yet", "The scanner records every evaluation here, NO TRADE included.")}</section>`;
          return;
        }
        const r = await TA.Signals.getBacktests();
        if (!host.isConnected) return;
        if (r.status !== "ok") { host.innerHTML = `<section class="card">${r.status === "disconnected" ? offline() : state("error", "Couldn't load backtests", TA.esc(r.error), retryBtn)}</section>`; return; }
        if (!r.data.runs.length) { host.innerHTML = `<section class="card">${state("empty", "No backtests yet", "Run one on the server: <code>python -m app.backtest --symbol BTCUSDT --market spot --days 180</code>")}</section>`; return; }
        host.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("flask")}Backtest runs</h2><span class="badge badge-demo">Historical simulation</span></div>
          <div class="table-wrap"><table><thead><tr><th>Run</th><th>Period</th><th class="r">Trades</th><th class="r">Expectancy</th><th class="r">Out-of-sample</th><th class="r">Walk-forward</th><th></th></tr></thead><tbody>
          ${r.data.runs.map((x) => `<tr><td>${TA.esc(x.symbol)} · ${x.market} · ${x.timeframe}<br/><span class="muted" style="font-size:.78rem">${TA.esc(x.strategy)}</span></td><td>${x.data_from.slice(0, 10)} → ${x.data_to.slice(0, 10)}</td><td class="r num">${x.trades}</td><td class="r num">${r2(x.expectancy_r)}</td><td class="r num">${x.oos_trades} · ${r2(x.oos_expectancy_r)}</td><td class="r num">${x.walk_forward_trades} · ${r2(x.walk_forward_expectancy_r)}</td><td><button class="btn btn-sm" data-run="${x.id}">Details</button></td></tr>`).join("")}</tbody></table></div><div id="runDetail"></div></section>`;
        host.querySelectorAll("[data-run]").forEach((b) => b.addEventListener("click", async () => {
          const d = await TA.Signals.getBacktest(b.dataset.run), box = $("#runDetail", host);
          if (d.status !== "ok") { box.innerHTML = state("error", "Couldn't load this run", TA.esc(d.error)); return; }
          const x = d.data, sp = x.splits, wf = x.walk_forward;
          box.innerHTML = `<h3 style="margin:18px 0 6px">${TA.esc(x.symbol)} · ${x.timeframe} · ${x.bars} candles</h3>
            <p class="muted" style="font-size:.82rem;margin:0 0 10px">${TA.esc(x.disclaimer)} Assumptions: fee ${((x.assumptions.fee_rate_per_side || 0) * 100).toFixed(3)}% and slippage ${(x.assumptions.slippage_per_side * 100).toFixed(3)}% per side, funding ${(x.assumptions.funding_rate_8h * 100).toFixed(4)}%/8h, latency ${x.assumptions.latency_bars} candle(s), same-candle rule: ${TA.esc(x.assumptions.same_candle_rule)}.</p>
            ${metricCards(x.full_period.metrics)}${curve(x.full_period.metrics.equity_curve)}
            <h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:16px 0 8px">Chronological periods</h3>
            <div class="table-wrap"><table><thead><tr><th>Period</th><th>Dates</th><th class="r">Trades</th><th class="r">Win rate</th><th class="r">Expectancy</th><th class="r">Total</th></tr></thead><tbody>
              ${["development", "validation", "out_of_sample"].map((k) => { const m = sp[k].metrics; return `<tr><td>${k.replace(/_/g, "-")}${k === "out_of_sample" ? ' <span class="badge badge-info">untouched</span>' : ""}</td><td>${(sp[k].from || "").slice(0, 10)} → ${(sp[k].to || "").slice(0, 10)}</td><td class="r num">${m.trades}</td><td class="r num">${pct(m.win_rate)}</td><td class="r num">${r2(m.expectancy_r)}</td><td class="r num">${r2(m.total_r)}</td></tr>`; }).join("")}</tbody></table></div>
            <h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:16px 0 8px">Walk-forward (test windows only)</h3>
            <div class="table-wrap"><table><thead><tr><th>Test window</th><th class="r">Chosen min score / R:R</th><th class="r">Trades</th><th class="r">Total</th></tr></thead><tbody>
              ${wf.folds.map((f) => `<tr><td>${f.test_from.slice(0, 10)} → ${f.test_to.slice(0, 10)}</td><td class="r num">${f.chosen_min_score} / ${f.chosen_min_rr}</td><td class="r num">${f.test_trades}</td><td class="r num">${r2(f.test_total_r)}</td></tr>`).join("")}</tbody></table></div>
            <p style="font-size:.86rem">Walk-forward combined: ${wf.out_of_sample_metrics.trades} trades, expectancy ${r2(wf.out_of_sample_metrics.expectancy_r)}.</p>
            ${breakdown("By side", x.full_period.metrics.by_side)}${breakdown("By exit", x.full_period.metrics.by_exit)}${breakdown("By regime", x.full_period.metrics.by_regime)}`;
          box.scrollIntoView({ behavior: TA.reducedMotion() ? "auto" : "smooth", block: "start" });
        }));
      }
      show("prospective");
    },

    risk(el) {
      const W = C.watchlist;
      el.innerHTML = `<div class="grid-dash">
        <section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("gauge")}Position size calculator</h2><span class="badge badge-info">Calculation only</span></div>
          <form id="rf" class="form-grid" novalidate>
            <div class="field"><label for="rsym">Market</label><select id="rsym">${W.map((w, i) => `<option value="${i}">${w.symbol} · ${w.market}</option>`).join("")}<option value="custom">Other / manual</option></select><span class="hint" id="h-rsym">Loads tick size, lot size and minimums from the exchange.</span></div>
            <div class="field"><label for="side">Direction</label><select id="side"><option>LONG</option><option>SHORT</option></select><span class="err" id="e-side"></span></div>
            ${fld("bal", "Account balance (USDT)", 1000, "Funds in this account.")}
            ${fld("riskPct", "Risk per trade (%)", 1, "Many traders use 0.5–2%.")}
            <div class="field"><label for="entry">Entry price</label><div style="display:flex;gap:6px"><input id="entry" inputmode="decimal" aria-describedby="h-entry e-entry" style="flex:1"/><button type="button" class="btn btn-sm" id="usePx">Use price</button></div><span class="hint" id="h-entry">Your planned entry.</span><span class="err" id="e-entry"></span></div>
            ${fld("stop", "Stop-loss price", "", "Where the idea is wrong.")}
            ${fld("lev", "Leverage (Futures)", 1, "Spot is always 1×.")}
            ${fld("fee", "Fee per side (%)", 0.1, "Taker fee; Binance base is ~0.1% spot, ~0.05% futures.")}
            ${fld("slip", "Slippage per side (%)", 0.05, "Allowance for fills worse than planned.")}
            ${fld("hold", "Expected holding time (hours)", 0, "Futures only: used to estimate funding.")}
            <div style="grid-column:1/-1;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="btn btn-primary" type="submit">Calculate</button><span class="muted" id="specInfo" style="font-size:.8rem"></span></div>
          </form></section>
        <section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("target")}Result</h2></div><div id="rr" aria-live="polite">${state("empty", "Enter your numbers", "Size is calculated from your risk and stop distance, including estimated fees and slippage. Nothing is sent to any exchange.")}</div></section></div>`;
      function fld(id, label, val, hint) { return `<div class="field"><label for="${id}">${label}</label><input id="${id}" inputmode="decimal" value="${val}" aria-describedby="h-${id} e-${id}"/><span class="hint" id="h-${id}">${hint}</span><span class="err" id="e-${id}"></span></div>`; }
      let specs = null, funding = null, lastPx = null;
      const sel = $("#rsym", el), info = $("#specInfo", el);
      const cur = () => (sel.value === "custom" ? null : W[+sel.value]);
      const isFut = () => (cur() ? cur().market === "Futures" : false);
      async function loadMarket() {
        specs = funding = lastPx = null;
        const w = cur();
        $("#lev", el).disabled = !w || !isFut(); if (!isFut()) $("#lev", el).value = 1;
        $("#hold", el).disabled = !isFut();
        $("#fee", el).value = isFut() ? 0.05 : 0.1;
        if (!w) { info.textContent = "Manual mode: no exchange rounding applied."; return; }
        info.textContent = "Loading exchange specs…";
        const [sp, tk, pr] = await Promise.all([TA.MarketData.getSpecs(w.symbol, w.market), TA.MarketData.getWatchlist({}), isFut() ? TA.MarketData.getPremium(w.symbol) : Promise.resolve(null)]);
        if (!el.isConnected || cur() !== w) return;
        if (sp.status === "ok") { specs = sp.data; info.textContent = `${specs.source}: tick ${specs.tick_size ?? "—"}, step ${specs.step_size}, min order ${specs.min_notional ?? "—"} USDT${specs.mmr ? `, maint. margin ${(specs.mmr * 100).toFixed(2)}%` : ""}`; }
        else info.textContent = `Couldn't load exchange specs (${sp.error || "not connected"}). Sizing will not be rounded.`;
        const row = tk.status === "ok" && tk.data.find((x) => x.symbol === w.symbol && x.market === w.market);
        if (row) lastPx = row.last;
        if (pr && pr.status === "ok") funding = pr.data.fundingRate;
      }
      sel.addEventListener("change", loadMarket);
      $("#usePx", el).addEventListener("click", () => { if (lastPx) $("#entry", el).value = lastPx; else TA.toast("Current price not loaded yet", "info"); });
      loadMarket();
      $("#rf", el).addEventListener("submit", (e) => {
        e.preventDefault();
        const v = (id) => parseFloat($("#" + id, el).value);
        ["bal", "riskPct", "entry", "stop", "lev", "fee", "slip", "hold"].forEach((id) => { $("#e-" + id, el).textContent = ""; $("#" + id, el).removeAttribute("aria-invalid"); });
        const req = { bal: v("bal"), riskPct: v("riskPct"), entry: v("entry"), stop: v("stop") };
        let bad = false;
        Object.entries(req).forEach(([k, x]) => { if (!(x > 0)) { $("#e-" + k, el).textContent = "Enter a number above 0."; $("#" + k, el).setAttribute("aria-invalid", "true"); bad = true; } });
        if (bad) { $("#rr", el).innerHTML = state("error", "Check the highlighted fields", "Fix the inputs and calculate again."); return; }
        const r = TA.Risk.sizePosition({ balance: req.bal, riskPct: req.riskPct, entry: req.entry, stop: req.stop, side: $("#side", el).value,
          market: isFut() ? "futures" : "spot", leverage: v("lev") || 1, feeRate: (v("fee") || 0) / 100, slippage: (v("slip") || 0) / 100,
          specs, fundingRate: funding, holdHours: v("hold") || 0 });
        if (!r.valid) { $("#rr", el).innerHTML = state("error", "Can't size this trade", r.errors.map(TA.esc).join(" ")); return; }
        const R = (k, val, tip) => `<div class="result"><small>${tip ? term(k, tip) : k}</small><div>${val}</div></div>`;
        const qtyTxt = `${r.qty} ${cur() ? cur().symbol.split("/")[0] : "units"}`;
        $("#rr", el).innerHTML = `<div class="result-grid">
            ${R("Position size", qtyTxt, "Rounded down to the exchange's lot step, so the risk never exceeds your limit.")}
            ${R("Order value", "$" + TA.fmtPrice(r.notional))}
            ${R("Amount at risk", `$${TA.fmtPrice(r.actual_risk)} (${r.actual_risk_pct.toFixed(2)}%)`, "Loss if the stop fills, including estimated fees and slippage on both sides.")}
            ${R("Margin used", "$" + TA.fmtPrice(r.margin), "Order value ÷ leverage.")}
            ${R("Fees at stop (est.)", "$" + TA.fmtPrice(r.fees_at_stop))}
            ${R("Entry / stop (tick-rounded)", `${r.entry_rounded} / ${r.stop_rounded}`)}
            ${r.liquidation_price != null ? R("Liquidation (est.)", `<span class="${r.liquidation_before_stop ? "down" : ""}">${TA.fmtPrice(r.liquidation_price)}</span>`, "Simplified isolated-margin estimate. The exchange's real level can differ.") : ""}
            ${r.funding_cost != null ? R("Funding over hold (est.)", `${r.funding_cost >= 0 ? "you pay" : "you receive"} $${TA.fmtPrice(Math.abs(r.funding_cost))}`, "Current funding rate × holding time ÷ 8h. Rates change every period.") : ""}
          </div>
          ${r.warnings.length ? `<ul style="margin:14px 0 0;padding-left:18px;color:var(--down);font-size:.86rem">${r.warnings.map((w) => `<li>${TA.esc(w)}</li>`).join("")}</ul>` : ""}
          <p class="muted" style="font-size:.78rem;margin:12px 0 0">${TA.esc(r.assumptions.note)} Leverage changes the margin and how close liquidation is, not the amount at risk to your stop. Not financial advice; TRADE-AI never places orders.</p>`;
        TA.toast("Position size calculated", "check");
      });
    },

    async alerts(el) {
      el.innerHTML = `<section class="card panel" id="notif"></section><section class="card panel"><div class="panel-head"><h2>${TA.icon("bell")}Alerts</h2><span class="muted" style="font-size:.82rem">Refreshes every 30s</span></div><div id="al"></div></section>`;
      const host = $("#al", el);
      const nh = $("#notif", el);
      const drawNotif = async () => {
        if (!TA.Auth.available()) { nh.remove(); return; }
        const info = await TA.Delivery.info(), sub = await TA.Delivery.current().catch(() => null);
        if (!nh.isConnected) return;
        const pushOn = Boolean(sub), canPush = TA.Delivery.pushSupported() && info.push_public_key;
        const ios = /iPhone|iPad/.test(navigator.userAgent) && !window.navigator.standalone;
        nh.innerHTML = `<div class="panel-head"><h2>${TA.icon("bell")}Notifications</h2></div>
          <p class="muted" style="margin:0 0 12px;font-size:.86rem">Get told when a new LONG or SHORT setup appears. Notifications show the pair, direction and score; levels stay in the app. Analysis only, not advice.</p>
          <div style="display:grid;gap:12px">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
              <div><b>Browser notifications</b><div class="muted" style="font-size:.82rem">${!canPush ? (ios ? "On iPhone/iPad: tap Share → Add to Home Screen, open TRADE-AI from there, then turn this on." : "Not supported in this browser.") : pushOn ? "On for this browser." : "Pops up on this device, even when the site is closed."}</div></div>
              ${canPush ? `<button class="btn btn-sm ${pushOn ? "" : "btn-primary"}" id="pushBtn">${pushOn ? "Turn off" : "Turn on"}</button>` : ""}</div>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
              <div><b>Email alerts</b><div class="muted" style="font-size:.82rem">${!info.email_available ? "Coming soon." : !TA.Auth.signedIn() ? `<a href="#/account">Sign in</a> to get new signals by email.` : info.email_alerts ? "On: sent to your account email." : "Off."}</div></div>
              ${info.email_available && TA.Auth.signedIn() ? `<button class="btn btn-sm ${info.email_alerts ? "" : "btn-primary"}" id="mailBtn">${info.email_alerts ? "Turn off" : "Turn on"}</button>` : ""}</div></div>`;
        const pb = $("#pushBtn", nh);
        if (pb) pb.addEventListener("click", async () => {
          pb.disabled = true;
          const r = pushOn ? await TA.Delivery.disablePush() : await TA.Delivery.enablePush(info.push_public_key).catch((e) => ({ ok: false, error: e.message }));
          TA.toast(r.ok ? (pushOn ? "Browser notifications off." : "Browser notifications on.") : r.error, r.ok ? "success" : "error");
          drawNotif(); const nb = $("#notifBanner"); if (nb && r.ok && !pushOn) nb.hidden = true;
        });
        const mb = $("#mailBtn", nh);
        if (mb) mb.addEventListener("click", async () => {
          mb.disabled = true;
          const r = await TA.Delivery.setEmail(!info.email_alerts);
          TA.toast(r.ok ? (info.email_alerts ? "Email alerts off." : "Email alerts on.") : r.error, r.ok ? "success" : "error");
          drawNotif();
        });
      };
      drawNotif();
      const load = async () => {
        const r = await TA.Signals.getAlerts(0);
        if (!host.isConnected) return;
        if (r.status === "disconnected") { host.innerHTML = state("off", "Alerts need the TRADE-AI server", "Alerts are created by the server when a new setup appears or a signal is triggered, hits a target, is stopped, expires or is invalidated. Set <code>api.backendBaseUrl</code> once the backend is hosted."); return; }
        if (r.status === "error") { host.innerHTML = state("error", "Couldn't load alerts", TA.esc(r.error), retryBtn); return; }
        if (!r.data.length) { host.innerHTML = state("empty", "No alerts yet", "You'll see new setups and lifecycle changes here."); return; }
        const icon = (k) => ({ new_signal: "zap", triggered: "target", stopped: "x", expired: "clock", invalidated: "alert" }[k] || (k.startsWith("tp") ? "check" : "bell"));
        host.innerHTML = `<ul class="list-signals" style="list-style:none;margin:0;padding:0">${r.data.map((a) => `<li class="sig-row" style="cursor:default"><span class="${a.kind === "stopped" || a.kind === "invalidated" ? "down" : a.kind.startsWith("tp") ? "up" : ""}">${TA.icon(icon(a.kind))}</span><span><b>${TA.esc(a.title)}</b><br/><span class="muted" style="font-size:.82rem">${TA.esc(a.message)}</span></span><span class="muted" style="font-size:.78rem">${TA.fmtTime(a.created_at)}</span></li>`).join("")}</ul>`;
        try { localStorage.setItem("ta-alert-seen", String(r.data[0].id)); } catch {}
        renderAlertBadge();
      };
      await load();
      every(30000, load);
    },

    async patterns(el) {
      if (!(await proGate(el, "Pattern & SMC analysis", "Structure breaks, liquidity, order blocks, fair value gaps, candlestick patterns and chart formations for any watchlist pair."))) return;
      const W = C.watchlist; let si = 0, tf = "1H";
      el.innerHTML = `<section class="card panel"><div class="panel-head" style="flex-wrap:wrap;gap:10px"><h2>${TA.icon("layers")}Pattern &amp; SMC analysis</h2>
          <div style="display:flex;gap:8px;flex-wrap:wrap"><select id="psym" aria-label="Symbol">${W.map((w, i) => `<option value="${i}">${TA.esc(w.symbol)} · ${w.market}</option>`).join("")}</select>
          <div class="seg" role="group" aria-label="Timeframe">${["15m", "1H", "4H", "1D"].map((x) => `<button data-ptf="${x}" aria-pressed="${x === tf}">${x}</button>`).join("")}</div></div></div>
        <p class="muted" style="margin:0;font-size:.85rem">Smart-money-concept structure and classic patterns detected on closed candles, each with where and when it formed. These are descriptions of the chart, not predictions or advice.</p></section>
        <div id="pout"></div>`;
      const out = $("#pout", el);
      const sec = (title, tip, body) => `<section class="card panel"><h2 style="font-size:1rem">${tip ? term(title, tip) : title}</h2>${body}</section>`;
      const tbl = (head, rows, empty) => rows.length ? `<div class="table-wrap"><table><thead><tr>${head.map((h, i) => `<th class="${i && /Price|Low|High|Level|Distance/.test(h) ? "r" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : `<p class="muted" style="margin:0;font-size:.88rem">${empty}</p>`;
      const bias = (b) => b === "bullish" ? `<span class="badge badge-long">Bullish</span>` : b === "bearish" ? `<span class="badge badge-short">Bearish</span>` : `<span class="badge badge-none">${TA.esc(b || "—")}</span>`;
      async function load() {
        if (store.demo) { out.innerHTML = `<section class="card">${state("off", "Uses live market data", "Turn off sample data to analyse real pairs.")}</section>`; return; }
        out.innerHTML = `<div class="skeleton" style="height:320px;border-radius:18px"></div>`;
        const w = W[si], r = await TA.MarketData.getCandles(w.symbol, w.market, tf, { limit: 300 });
        if (!el.isConnected) return;
        if (r.status !== "ok") { out.innerHTML = `<section class="card">${fromResult(r, "Candles")}</section>`; return; }
        const cs = r.data.slice(0, -1), t = cs.map((x) => x.t), o = cs.map((x) => x.o), h = cs.map((x) => x.h), l = cs.map((x) => x.l), c = cs.map((x) => x.c);
        const px = c[c.length - 1], n = cs.length, when = (i) => (i == null || !t[i] ? "—" : TA.fmtTime(t[i]));
        const dist = (lo, hi) => { const m = px > hi ? (px - hi) / px : px < lo ? (lo - px) / px : 0; return m === 0 ? "Price inside" : `${px > hi ? "−" : "+"}${(m * 100).toFixed(2)}%`; };
        const S = TA.SMC.analyzeSmc(o, h, l, c), A = TA.Analysis;
        const pd = S.premium_discount, ev = S.structure.slice(-6).reverse();
        const live = (z) => !["filled", "broken", "mitigated"].includes(z.status);
        const obs = S.order_blocks.filter(live).slice(-8).reverse(), fvgs = S.fvgs.filter(live).slice(-8).reverse();
        const liq = S.liquidity.levels.filter((x) => x.status === "resting"), above = liq.filter((x) => x.level > px).sort((a, b) => a.level - b.level).slice(0, 4), below = liq.filter((x) => x.level < px).sort((a, b) => b.level - a.level).slice(0, 4);
        const sweeps = S.liquidity.levels.filter((x) => x.status === "swept").slice(-5).reverse();
        const pats = A.detectCandlestickPatterns(o, h, l, c).filter((p) => p.index >= n - 12).reverse();
        const forms = A.doubleTopsBottoms(h, l, c).slice(-4).reverse();
        out.innerHTML = `<div class="grid-dash">
          <section class="card panel span-12"><div class="result-grid" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr))">
            <div class="result"><small>Last price</small><div>${TA.fmtPrice(px)}</div></div>
            <div class="result"><small>${term("Structure", "Direction of the latest break of structure (BOS) or change of character (CHOCH).")}</small><div>${bias(S.trend)}</div></div>
            <div class="result"><small>${term("Premium / discount", "Where price sits in the recent swing range. Above the midpoint = premium, below = discount.")}</small><div>${!pd ? "—" : pd.position < 0 ? "Below the range" : pd.position > 1 ? "Above the range" : `${pd.zone[0].toUpperCase() + pd.zone.slice(1)} · ${(pd.position * 100).toFixed(0)}%`}</div></div>
            <div class="result"><small>Candles analysed</small><div>${n} × ${tf}</div></div></div>
            <p class="muted" style="margin:10px 0 0;font-size:.8rem">Source: ${TA.esc(r.sourceName)} · last closed candle ${when(n - 1)}</p></section>
          <div class="span-6">${sec("Structure breaks", "BOS = trend continues past a swing. CHOCH = first break against the prior trend.", tbl(["Type", "Direction", "Level", "When"], ev.map((e) => `<tr><td><b>${e.type}</b></td><td>${bias(e.direction)}</td><td class="r num">${TA.fmtPrice(e.level)}</td><td class="muted">${when(e.index)}</td></tr>`), "No structure breaks in this window."))}</div>
          <div class="span-6">${sec("Liquidity", "Resting liquidity = untouched swing highs (buy-side) and lows (sell-side) where stops tend to cluster.", tbl(["Side", "Level", "Distance", "Status"], [...above.map((x) => ["Buy-side above", x]), ...below.map((x) => ["Sell-side below", x])].map(([k, x]) => `<tr><td>${k}</td><td class="r num">${TA.fmtPrice(x.level)}</td><td class="r num">${dist(x.level, x.level)}</td><td class="muted">Resting since ${when(x.index)}</td></tr>`).concat(sweeps.map((x) => `<tr><td>${x.side === "BSL" ? "Buy-side" : "Sell-side"} sweep</td><td class="r num">${TA.fmtPrice(x.level)}</td><td class="r num">—</td><td class="muted">Swept ${when(x.event_index)}</td></tr>`)), "No resting liquidity levels found."))}</div>
          <div class="span-6">${sec("Order blocks", "The last opposite candle before a move that broke structure. Shown while not yet broken or fully mitigated.", tbl(["Bias", "Low", "High", "Distance", "Formed"], obs.map((z) => `<tr><td>${bias(z.direction)}</td><td class="r num">${TA.fmtPrice(z.low)}</td><td class="r num">${TA.fmtPrice(z.high)}</td><td class="r num">${dist(z.low, z.high)}</td><td class="muted">${when(z.index)} · ${TA.esc(z.status)}</td></tr>`), "No active order blocks."))}</div>
          <div class="span-6">${sec("Fair value gaps", "Three-candle imbalances where price moved too fast to trade both ways. Shown until filled.", tbl(["Bias", "Low", "High", "Distance", "Formed"], fvgs.map((z) => `<tr><td>${bias(z.direction)}</td><td class="r num">${TA.fmtPrice(z.low)}</td><td class="r num">${TA.fmtPrice(z.high)}</td><td class="r num">${dist(z.low, z.high)}</td><td class="muted">${when(z.index)} · ${TA.esc(z.status)}</td></tr>`), "No unfilled fair value gaps."))}</div>
          <div class="span-6">${sec("Candlestick patterns (last 12 candles)", "Single- and multi-candle patterns. On their own they have weak predictive value; read them with structure and context.", tbl(["Pattern", "Bias", "Candle"], pats.map((p) => `<tr><td><b>${TA.esc(p.pattern)}</b></td><td>${bias(p.bias)}</td><td class="muted">${when(p.index)}</td></tr>`), "No candlestick patterns in the last 12 candles."))}</div>
          <div class="span-6">${sec("Chart formations", "Double tops/bottoms with their neckline. Confirmed once price closes through the neckline.", tbl(["Formation", "Bias", "Neckline", "Status"], forms.map((f) => `<tr><td><b>${TA.esc(f.formation)}</b></td><td>${bias(f.bias)}</td><td class="r num">${TA.fmtPrice(f.neckline)}</td><td class="muted">${f.status === "confirmed" ? `Confirmed ${when(f.confirmed_index)}` : "Forming"}</td></tr>`), "No double tops or bottoms detected."))}</div>
        </div>`;
      }
      $("#psym", el).addEventListener("change", (e) => { si = +e.target.value; load(); });
      el.querySelectorAll("[data-ptf]").forEach((b) => b.addEventListener("click", () => { tf = b.dataset.ptf; el.querySelectorAll("[data-ptf]").forEach((x) => x.setAttribute("aria-pressed", x === b)); load(); }));
      load();
      every(120000, load);
    },

    async futures(el) {
      if (!(await proGate(el, "Futures intelligence", "Funding rates, open interest, long/short positioning and mark-vs-index premium across the top perpetual contracts."))) return;
      const B = TA.Providers && TA.Providers.binance;
      let sel = "BTCUSDT", board = null, sortKey = "quoteVolume", dir = -1;
      el.innerHTML = `<div id="fdet"></div><section class="card panel"><div class="panel-head"><h2>${TA.icon("chart")}Perpetual futures board</h2><button class="btn btn-sm" id="frefresh">${TA.icon("refresh", "icon-sm")}Refresh</button></div>
        <p class="muted" style="margin:0 0 12px;font-size:.85rem">Top 30 crypto USDT-M perpetuals on Binance by 24h volume (stock and commodity contracts excluded). Click a row for open interest, funding history and positioning. These are market readings, not signals or advice.</p>
        <div id="fboard"></div><p class="muted" id="fmeta" style="font-size:.8rem;margin:10px 0 0"></p></section>`;
      const det = $("#fdet", el), bh = $("#fboard", el);
      if (store.demo || !B) { bh.innerHTML = state("off", "Uses live futures data", "Turn off sample data to load real futures data."); return; }
      const pct = (v, d = 4) => (v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`);
      const fcls = (v) => (v > 0.0001 ? "up" : v < 0 ? "down" : "");
      const cols = [["symbol", "Contract", ""], ["mark", "Mark", ""], ["change", "24h", ""], ["funding", "Funding", "Rate per funding payment (usually every 8h). Positive = longs pay shorts (crowded long); negative = shorts pay longs."],
        ["annual", "Funding / yr", "Current rate × payments per day × 365 (most contracts pay every 8h, some every 4h or 1h). Rates change every period, so this is illustrative."], ["basis", "Mark vs index", "Perp mark price premium (+) or discount (−) to the spot index."], ["quoteVolume", "24h volume", ""]];
      const drawBoard = () => {
        const list = board.slice().sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * dir);
        bh.innerHTML = `<div class="table-wrap"><table><thead><tr>${cols.map(([k, l, tip], i) => `<th class="${i ? "r" : ""}"><button data-fsort="${k}" style="all:unset;cursor:pointer">${tip ? `<span class="term" data-tip="${tip}">${l}</span>` : l}${sortKey === k ? (dir > 0 ? " ▲" : " ▼") : ""}</button></th>`).join("")}</tr></thead><tbody>
          ${list.map((r) => `<tr data-fsym="${r.symbol}" style="cursor:pointer${r.symbol === sel ? ";background:rgba(54,214,231,.07)" : ""}" tabindex="0"><td><b>${r.symbol.replace(/USDT$/, "/USDT")}</b></td><td class="r num">${TA.fmtPrice(r.mark)}</td><td class="r">${TA.chg(r.change)}</td>
            <td class="r num ${fcls(r.funding)}">${pct(r.funding)}${r.intervalHours !== 8 ? ` <span class="muted" style="font-size:.75rem">/${r.intervalHours}h</span>` : ""}</td><td class="r num ${fcls(r.funding)}">${pct(r.annual, 1)}</td><td class="r num">${pct(r.basis, 3)}</td><td class="r num">${TA.fmtCompact(r.quoteVolume)}</td></tr>`).join("")}</tbody></table></div>`;
      };
      const spark = (vals, color = "var(--accent, #36D6E7)") => {
        const v = vals.filter((x) => x != null); if (v.length < 2) return "";
        const W = 300, H = 60, lo = Math.min(...v), hi = Math.max(...v), y = (x) => H - 4 - ((x - lo) / (hi - lo || 1)) * (H - 8);
        return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="60" preserveAspectRatio="none" role="img" aria-label="trend"><polyline fill="none" stroke="${color}" stroke-width="2" points="${v.map((x, i) => `${(i / (v.length - 1)) * W},${y(x)}`).join(" ")}"/></svg>`;
      };
      const loadDetail = async () => {
        det.innerHTML = `<div class="skeleton" style="height:220px;border-radius:18px;margin-bottom:16px"></div>`;
        try {
          const d = await B.futuresDetail(sel), row = board && board.find((x) => x.symbol === sel);
          if (!el.isConnected) return;
          const oi = d.oi, oiNow = oi.length ? oi[oi.length - 1] : null, oi24 = oi.length > 24 ? oi[oi.length - 25] : oi[0];
          const oiChg = oiNow && oi24 && oi24.usd ? (oiNow.usd - oi24.usd) / oi24.usd : null;
          const fr = d.funding, avgF = fr.length ? fr.reduce((s, x) => s + x.rate, 0) / fr.length : null;
          const acc = d.accounts.length ? d.accounts[d.accounts.length - 1] : null, top = d.top.length ? d.top[d.top.length - 1] : null;
          const read = [];
          if (oiChg != null && row) read.push(oiChg > 0.03 && row.change > 0 ? "Open interest and price both rose over 24h: new positions are being added on the way up." : oiChg > 0.03 && row.change < 0 ? "Open interest rose while price fell: new positions are being added on the way down (often shorts)." : oiChg < -0.03 && row.change > 0 ? "Price rose while open interest fell: the move looks driven by shorts closing." : oiChg < -0.03 && row.change < 0 ? "Price and open interest both fell: positions are being closed (long liquidation or de-risking)." : "Open interest is roughly flat over 24h.");
          if (row) read.push(row.funding > 0.0003 ? "Funding is well above the 0.01% baseline: longs are paying a lot to stay in (crowded long)." : row.funding < 0 ? "Funding is negative: shorts are paying longs (crowded short)." : "Funding is near the normal 0.01% baseline.");
          if (acc) read.push(`${(acc.long * 100).toFixed(0)}% of accounts are net long.`);
          det.innerHTML = `<section class="card panel" style="margin-bottom:16px"><div class="panel-head"><h2>${sel.replace(/USDT$/, "/USDT")} perpetual</h2><span class="badge">${TA.esc(d.source)}</span></div>
            <div class="result-grid" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr))">
              <div class="result"><small>${term("Open interest", "Total value of open contracts (USD).")}</small><div>${oiNow ? "$" + TA.fmtCompact(oiNow.usd) : "—"} <span class="${oiChg >= 0 ? "up" : "down"}" style="font-size:.85rem">${oiChg == null ? "" : pct(oiChg, 2) + " 24h"}</span></div>${spark(oi.map((x) => x.usd))}</div>
              <div class="result"><small>${term("Funding (last 30)", "Each settled funding rate, oldest to newest. Average shown.")}</small><div>${row ? pct(row.funding) : "—"} <span class="muted" style="font-size:.85rem">avg ${pct(avgF)}</span></div>${spark(fr.map((x) => x.rate), "#F16B75")}</div>
              <div class="result"><small>${term("Long/short accounts", "Ratio of accounts net long to net short (all traders).")}</small><div>${acc ? acc.ratio.toFixed(2) : "—"}</div>${spark(d.accounts.map((x) => x.ratio), "#35C98A")}</div>
              <div class="result"><small>${term("Top traders (positions)", "Long/short ratio of positions held by the top 20% of accounts by margin.")}</small><div>${top ? top.ratio.toFixed(2) : "—"}</div>${spark(d.top.map((x) => x.ratio), "#18B89A")}</div></div>
            <ul style="margin:12px 0 0;padding-left:18px;font-size:.88rem;color:var(--tx-2);display:grid;gap:4px">${read.map((x) => `<li>${x}</li>`).join("")}</ul>
            <p class="muted" style="margin:10px 0 0;font-size:.8rem">Charts cover the last 48 hours in 1-hour steps (funding: last 30 payments). Positioning data describes crowding, it doesn't predict direction. Next funding ${row ? TA.fmtTime(row.nextFunding) : "—"}.</p></section>`;
        } catch (e) { det.innerHTML = `<section class="card" style="margin-bottom:16px">${state("error", "Couldn't load futures detail", TA.esc(e.message || String(e)) + (e.kind === "region" ? " Binance Futures blocks some regions." : ""))}</section>`; }
      };
      const loadBoard = async () => {
        try {
          const all = await B.futuresBoard();
          board = all.sort((a, b) => b.quoteVolume - a.quoteVolume).slice(0, 30).map((r) => ({ ...r, annual: r.funding * (24 / r.intervalHours) * 365 }));
          if (!el.isConnected) return;
          drawBoard(); $("#fmeta", el).innerHTML = `Source: Binance USDT-M Futures · updated ${ageHtml(Date.now())}`;
        } catch (e) { bh.innerHTML = state("error", "Couldn't load futures data", TA.esc(e.message || String(e)) + (e.kind === "region" ? " Binance Futures isn't available from your network or region." : ""), `<button class="btn btn-sm" data-act="retry">Try again</button>`); }
      };
      el.addEventListener("click", (e) => {
        const r = e.target.closest("[data-fsym]"), s = e.target.closest("[data-fsort]"), f = e.target.closest("#frefresh");
        if (s) { const k = s.dataset.fsort; dir = sortKey === k ? -dir : (k === "symbol" ? 1 : -1); sortKey = k; drawBoard(); }
        else if (r) { sel = r.dataset.fsym; drawBoard(); loadDetail(); window.scrollTo({ top: 0, behavior: "smooth" }); }
        else if (f) { loadBoard().then(loadDetail); }
      });
      el.addEventListener("keydown", (e) => { const r = e.target.closest("[data-fsym]"); if (r && e.key === "Enter") r.click(); });
      await loadBoard(); loadDetail();
      every(60000, loadBoard);
    },

    async reset(el) {
      const token = new URLSearchParams((location.hash.split("?")[1]) || "").get("token");
      if (!token) { el.innerHTML = `<section class="card">${state("error", "This reset link is incomplete", "Open the link from your email again, or request a new one from Sign in.")}</section>`; return; }
      el.innerHTML = `<section class="card panel" style="max-width:520px"><div class="panel-head"><h2>${TA.icon("user")}Choose a new password</h2></div>
        <form class="auth-form" id="rsForm" novalidate>
          <div class="field"><label for="np">New password</label><input id="np" type="password" minlength="8" autocomplete="new-password" /><span class="hint">At least 8 characters.</span></div>
          <span class="err" id="rsErr" role="alert"></span><button class="btn btn-primary" type="submit">Save new password</button></form></section>`;
      $("#rsForm", el).addEventListener("submit", async (e) => {
        e.preventDefault();
        const r = await TA.Auth.reset(token, $("#np", el).value);
        if (!r.ok) { $("#rsErr", el).textContent = r.error; return; }
        TA.toast("Password updated. You're signed in.", "success");
        history.replaceState(null, "", location.pathname + location.search + "#/account"); route();
      });
    },

    async stats(el) {
      if (!TA.Auth.available() || !TA.Auth.signedIn()) { el.innerHTML = `<section class="card">${state("off", "Sign in as an admin", "Usage stats are only visible to admin accounts.")}</section>`; return; }
      let days = 30;
      const draw = async () => {
        el.innerHTML = `<div class="skeleton" style="height:260px;border-radius:18px"></div>`;
        let d;
        try { d = await TA.Auth.stats(days); } catch (e) { el.innerHTML = `<section class="card">${state("error", "Can't show stats", TA.esc(e.message))}</section>`; return; }
        if (!el.isConnected) return;
        const sum = (k) => d.daily.reduce((a, x) => a + x[k], 0), max = Math.max(1, ...d.daily.map((x) => x.views));
        const T = d.totals;
        el.innerHTML = `<section class="card panel"><div class="panel-head"><h2>${TA.icon("chart")}Usage stats</h2>
            <div class="seg" role="group" aria-label="Range">${[7, 30, 90].map((n) => `<button data-sdays="${n}" aria-pressed="${n === days}">${n} days</button>`).join("")}</div></div>
          <div class="result-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
            <div class="result"><small>Page views</small><div>${sum("views").toLocaleString()}</div></div>
            <div class="result"><small>${term("Visits", "Unique visitor-page pairs per day, summed. A person viewing 3 pages on one day counts 3.")}</small><div>${sum("visitors").toLocaleString()}</div></div>
            <div class="result"><small>Accounts</small><div>${T.accounts}</div></div>
            <div class="result"><small>Paying</small><div>${T.paid}</div></div>
            <div class="result"><small>Trial unlocks</small><div>${T.unlocks}</div></div>
            <div class="result"><small>Signals generated</small><div>${T.signals}</div></div></div>
          <h3 style="font-size:.9rem;margin:18px 0 8px">Page views per day</h3>
          ${d.daily.length ? `<div style="display:flex;align-items:flex-end;gap:3px;height:120px" role="img" aria-label="Daily page views">${d.daily.map((x) => `<div title="${x.day}: ${x.views} views" style="flex:1;min-width:3px;height:${Math.max(3, (x.views / max) * 100)}%;background:linear-gradient(180deg,#36D6E7,#18B89A);border-radius:3px 3px 0 0;box-shadow:0 0 8px rgba(54,214,231,.35)"></div>`).join("")}</div>
            <div class="muted" style="display:flex;justify-content:space-between;font-size:.75rem;margin-top:4px"><span>${d.daily[0].day}</span><span>${d.daily[d.daily.length - 1].day}</span></div>` : `<p class="muted" style="margin:0">No visits recorded in this period yet.</p>`}
          <h3 style="font-size:.9rem;margin:18px 0 8px">Top pages</h3>
          ${d.pages.length ? `<div class="table-wrap"><table><thead><tr><th>Page</th><th class="r">Views</th><th class="r">Visits</th></tr></thead><tbody>${d.pages.map((p) => `<tr><td>${TA.esc(p.path)}</td><td class="r num">${p.views}</td><td class="r num">${p.visitors}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted" style="margin:0">Nothing yet.</p>`}
          <p class="muted" style="font-size:.8rem;margin:12px 0 0">${TA.esc(d.note)} Visitors with Do-Not-Track or Global Privacy Control switched on aren't counted.</p></section>`;
        el.querySelectorAll("[data-sdays]").forEach((b) => b.addEventListener("click", () => { days = +b.dataset.sdays; draw(); }));
      };
      draw();
    },

    async monitor(el) {
      if (!(await proGate(el, "Market risk monitor", "A tested trend model that reads whether the market is risk-on or risk-off, how much exposure it would hold, and which of the top-20 coins are trending."))) return;
      const B = TA.Providers && TA.Providers.binance, R = TA.Regime;
      el.innerHTML = `<div id="mon"><div class="skeleton" style="height:180px;border-radius:18px"></div></div>`;
      const host = $("#mon", el);
      if (store.demo || !B) { host.innerHTML = `<section class="card">${state("off", "Uses live market data", "Turn off sample data to run the model.")}</section>`; return; }
      const pct = (x, d = 0) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
      const dots = (subs) => `<span style="display:inline-flex;gap:3px" aria-label="${subs.filter((x) => x.on).length} of 9 lookbacks in trend">${subs.map((x) => `<i title="${x.lookback}-day: ${x.on ? "in trend" : "no trend"}" style="width:8px;height:8px;border-radius:50%;background:${x.on ? "#35C98A" : "rgba(145,163,176,.25)"};${x.on ? "box-shadow:0 0 6px rgba(53,201,138,.7)" : ""}"></i>`).join("")}</span>`;
      const load = async () => {
        const series = {}, failed = [];
        let k = 0;
        const worker = async () => { while (k < R.UNIVERSE.length) { const sym = R.UNIVERSE[k++];
          try { const r = await B.candles("Spot", sym.replace(/USDT$/, "/USDT"), "1D", 1000); const cs = r.candles.slice(0, -1);   // closed days only
                series[sym] = { t: cs.map((x) => x.t), c: cs.map((x) => x.c), v: cs.map((x) => x.v) };
          } catch { failed.push(sym); } } };
        await Promise.all(Array.from({ length: 5 }, worker));
        if (!el.isConnected) return;
        if (!series.BTCUSDT) { host.innerHTML = `<section class="card">${state("error", "Couldn't load market data", "Binance didn't respond. Try again in a minute.", `<button class="btn btn-sm" data-act="retry">Try again</button>`)}</section>`; return; }
        // align every coin to BTC's last closed day
        const lastT = series.BTCUSDT.t[series.BTCUSDT.t.length - 1];
        for (const [s, d] of Object.entries(series)) { const n = d.t.filter((t) => t <= lastT).length; if (!n || d.t[n - 1] !== lastT) { delete series[s]; failed.push(s); continue; } series[s] = { t: d.t.slice(0, n), c: d.c.slice(0, n), v: d.v.slice(0, n) }; }
        const m = R.evaluate(series), on = m.regime === "risk-on";
        const btcOn = Math.round((m.btcScore || 0) * 9);
        const rows = m.rows.filter((r) => r.liq != null);
        host.innerHTML = `<div class="grid-dash">
          <section class="card panel span-12" style="border-color:${on ? "rgba(53,201,138,.45)" : "rgba(241,107,117,.45)"};box-shadow:0 0 24px ${on ? "rgba(53,201,138,.12)" : "rgba(241,107,117,.12)"}">
            <div class="panel-head"><h2>${TA.icon("shield")}Market regime</h2><span class="muted" style="font-size:.82rem">Daily model · as of ${new Date(lastT).toISOString().slice(0, 10)} close (UTC)</span></div>
            <div class="result-grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">
              <div class="result"><small>Regime</small><div style="color:${on ? "#35C98A" : "#F16B75"};font-weight:800">${on ? "▲ RISK-ON" : "▼ RISK-OFF"}</div></div>
              <div class="result"><small>${term("BTC trend", "How many of BTC's 9 trend lookbacks (5 to 360 days) are in an uptrend. Under 5 of 9 = risk-off: the model halves all positions.")}</small><div>${btcOn} of 9</div></div>
              <div class="result"><small>${term("Model exposure", "Share of a portfolio the tested model would hold in coins now. The rest stays in cash.")}</small><div>${pct(m.exposure)}</div></div>
              <div class="result"><small>Coins in trend</small><div>${rows.filter((r) => r.eligible && r.score > 0).length} of ${rows.filter((r) => r.eligible).length}</div></div></div>
            <p style="margin:12px 0 0;font-size:.9rem;color:var(--tx-2)">${on
              ? "Bitcoin is in a broad uptrend. In past risk-on periods the model held more coins. Trends can reverse quickly; this is a reading, not a forecast."
              : "Bitcoin is not in a broad uptrend. In this state the model cuts its positions in half or holds cash. In the unseen 2022–23 bear market, this is how it lost 11.5% while holding the top 20 coins lost 55%."}</p></section>
          <section class="card panel span-12"><div class="panel-head"><h2>${TA.icon("layers")}Trend by coin</h2><span class="muted" style="font-size:.82rem">Top-20 by liquidity</span></div>
            <div class="table-wrap"><table><thead><tr><th>Coin</th><th class="r">Last close</th><th>${term("Trend lookbacks", "Each dot is one lookback (5, 10, 20, 30, 60, 90, 150, 250, 360 days). Green = price broke above its range and hasn't fallen below the trailing stop.")}</th><th class="r">${term("90-day volatility", "Annualised. Higher volatility means the model holds a smaller position.")}</th><th class="r">${term("Model weight", "What the tested model would hold, as a share of the portfolio. Max 5% per coin.")}</th></tr></thead><tbody>
            ${rows.filter((r) => r.eligible).sort((a, b) => b.score - a.score || b.liq - a.liq).map((r) => `<tr><td><b>${r.sym.replace(/USDT$/, "")}</b></td><td class="r num">${TA.fmtPrice(r.close)}</td><td>${dots(r.subs)}</td><td class="r num">${pct(r.vol)}</td><td class="r num ${r.weight > 0 ? "up" : "muted"}">${r.weight > 0 ? pct(r.weight, 1) : "—"}</td></tr>`).join("")}
            </tbody></table></div>
            ${failed.length ? `<p class="muted" style="font-size:.8rem;margin:8px 0 0">Unavailable: ${failed.map((s) => s.replace(/USDT$/, "")).join(", ")}.</p>` : ""}</section>
          <section class="card panel span-12"><h2 style="font-size:1rem">${TA.icon("info")}How this model was tested</h2>
            <p class="muted" style="margin:0 0 10px;font-size:.88rem">Pre-registered research round 4, based on published trend-following research. It was chosen on 2020–21 data and tested once on unseen 2022–23 data, with 0.15% costs and no leverage.</p>
            <div class="table-wrap"><table><thead><tr><th>Unseen test, 2022 → Nov 2023</th><th class="r">Return</th><th class="r">Worst drawdown</th></tr></thead><tbody>
              <tr><td><b>This model</b></td><td class="r num down">−11.5%</td><td class="r num">−34%</td></tr>
              <tr><td>Holding BTC</td><td class="r num down">−24.8%</td><td class="r num">−67%</td></tr>
              <tr><td>Holding top-20 coins</td><td class="r num down">−55.5%</td><td class="r num">−72%</td></tr></tbody></table></div>
            <p style="margin:10px 0 0;font-size:.86rem;color:var(--tx-2)"><b>Honest summary:</b> it cut losses and drawdowns sharply, but it didn't make a profit in the test, so it's a <b>risk tool, not a buy/sell signal</b>. Delisted coins aren't in the data, which flatters the results. <a href="https://github.com/Sahan308/trade-ai/blob/main/research/RESULTS.md" target="_blank" rel="noopener">Full results</a>. Not financial advice.</p></section></div>`;
      };
      await load();
      every(600000, load);
    },

    async scanner(el) {
      if (!(await proGate(el, "Market scanner", "Rank the 25 most-traded pairs by trend, ADX, RSI, MACD, volume spikes and volatility on 1H, 4H or 1D."))) return;
      const B = TA.Providers && TA.Providers.binance;
      const tfs = ["1H", "4H", "1D"];
      let tf = "1H", rows = null, sortKey = "adx", dir = -1, fil = "all", busy = false, at = null;
      el.innerHTML = `<section class="card panel">
        <div class="panel-head" style="flex-wrap:wrap;gap:10px"><h2>${TA.icon("radar")}Market scanner</h2>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div class="seg" role="group" aria-label="Timeframe">${tfs.map((x) => `<button data-stf="${x}" aria-pressed="${x === tf}">${x}</button>`).join("")}</div>
            <div class="seg" role="group" aria-label="Filter">${[["all", "All"], ["up", "Uptrend"], ["down", "Downtrend"], ["range", "Ranging"], ["vol", "Volume spike"]].map(([k, l]) => `<button data-sfil="${k}" aria-pressed="${k === fil}">${l}</button>`).join("")}</div>
            <button class="btn btn-sm" id="srefresh">${TA.icon("refresh", "icon-sm")}Rescan</button></div></div>
        <p class="muted" style="margin:0 0 12px;font-size:.85rem">The 25 most-traded USDT spot pairs on Binance, measured on closed candles. These are readings, not trade signals or advice. Click a column to sort.</p>
        <div id="scan"></div><p class="muted" id="smeta" style="font-size:.8rem;margin:10px 0 0"></p></section>`;
      const host = $("#scan", el);
      if (store.demo || !B) { host.innerHTML = state("off", "The scanner uses live market data", "Turn off sample data to scan real pairs."); return; }
      const cols = [["symbol", "Pair", "", false], ["last", "Last", "", true], ["change", "24h", "", true], ["trend", "Trend", "Price vs a rising/falling EMA 50 on this timeframe.", false],
        ["adx", "ADX", "Trend strength. Above 25 = trending, below 20 = ranging.", true], ["rsi", "RSI", "Momentum, 0–100. Above 70 stretched up, below 30 stretched down.", true],
        ["macd", "MACD", "Histogram sign: positive = upward momentum.", false], ["volx", "Vol ×", "Last 24 candles' volume vs the 24 before them.", true], ["atrp", "ATR %", "Average candle range as % of price (volatility).", true], ["qv", "24h volume", "", true]];
      const pass = (r) => fil === "all" || (fil === "up" && r.trend === "Up") || (fil === "down" && r.trend === "Down") || (fil === "range" && r.adx != null && r.adx < 20) || (fil === "vol" && r.volx != null && r.volx >= 1.5);
      const draw = () => {
        if (!rows) return;
        const list = rows.filter(pass).sort((a, b) => { const x = a[sortKey], y = b[sortKey]; return (x == null) - (y == null) || (x > y ? 1 : x < y ? -1 : 0) * dir; });
        const tr = (r) => `<tr><td><b>${TA.esc(r.symbol)}</b></td><td class="r num">${TA.fmtPrice(r.last)}</td><td class="r">${r.change == null ? "—" : TA.chg(r.change)}</td>
          <td>${r.trend === "Up" ? `<span class="badge badge-long">Up</span>` : r.trend === "Down" ? `<span class="badge badge-short">Down</span>` : `<span class="badge badge-none">Mixed</span>`}</td>
          <td class="r num">${fmtN(r.adx, 1)}</td><td class="r num ${r.rsi >= 70 ? "up" : r.rsi <= 30 ? "down" : ""}">${fmtN(r.rsi, 1)}</td>
          <td class="${r.macd > 0 ? "up" : r.macd < 0 ? "down" : ""}">${r.macd == null ? "—" : r.macd > 0 ? "Positive" : "Negative"}</td>
          <td class="r num ${r.volx >= 1.5 ? "up" : ""}">${r.volx == null ? "—" : r.volx.toFixed(2) + "×"}</td><td class="r num">${fmtN(r.atrp, 2)}</td><td class="r num">${TA.fmtCompact(r.qv)}</td></tr>`;
        host.innerHTML = list.length ? `<div class="table-wrap"><table><thead><tr>${cols.map(([k, l, tip, num]) => `<th class="${num ? "r" : ""}"><button class="linkish" data-ssort="${k}" style="all:unset;cursor:pointer">${tip ? `<span class="term" data-tip="${tip}">${l}</span>` : l}${sortKey === k ? (dir > 0 ? " ▲" : " ▼") : ""}</button></th>`).join("")}</tr></thead><tbody>${list.map(tr).join("")}</tbody></table></div>`
          : state("empty", "No pairs match this filter", "Try another filter or timeframe.");
      };
      const scan = async () => {
        if (busy) return; busy = true;
        host.innerHTML = `<div class="table-wrap"><table><tbody>${skRows(8, 6)}</tbody></table></div>`;
        try {
          const top = await B.topSpot(25);
          const out = []; let i = 0;
          const worker = async () => { while (i < top.length) { const p = top[i++];
            try {
              const r = await B.candles("Spot", p.symbol, tf, 200), cs = r.candles.slice(0, -1);   // drop the still-open candle
              const A = TA.Analysis, h = cs.map((x) => x.h), l = cs.map((x) => x.l), c = cs.map((x) => x.c), v = cs.map((x) => x.v);
              const e50 = A.ema(c, 50), last = c[c.length - 1], eNow = lastOf(e50), ePrev = e50[e50.length - 6];
              const sumV = (a, b) => v.slice(a, b).reduce((s, x) => s + x, 0), prev = sumV(-48, -24);
              out.push({ ...p, symbol: p.symbol, qv: p.quoteVolume,
                trend: eNow == null || ePrev == null ? "Mixed" : last > eNow && eNow > ePrev ? "Up" : last < eNow && eNow < ePrev ? "Down" : "Mixed",
                adx: lastOf(A.adx(h, l, c).adx), rsi: lastOf(A.rsi(c)), macd: lastOf(A.macd(c).histogram),
                volx: prev > 0 ? sumV(-24) / prev : null, atrp: last ? (lastOf(A.atr(h, l, c)) / last) * 100 : null });
            } catch {} } };
          await Promise.all(Array.from({ length: 5 }, worker));
          if (!el.isConnected) return;
          rows = out; at = Date.now(); draw();
          $("#smeta", el).innerHTML = `Source: Binance Spot · ${out.length} of ${top.length} pairs · ${tf} candles · scanned ${ageHtml(at)}`;
        } catch (e) { host.innerHTML = state("error", "Couldn't scan the market", TA.esc(e.message || String(e)), `<button class="btn btn-sm" data-act="retry">Try again</button>`); }
        finally { busy = false; }
      };
      el.addEventListener("click", (e) => {
        const b = e.target.closest("[data-stf],[data-sfil],[data-ssort],#srefresh"); if (!b) return;
        if (b.dataset.stf) { tf = b.dataset.stf; el.querySelectorAll("[data-stf]").forEach((x) => x.setAttribute("aria-pressed", x === b)); scan(); }
        else if (b.dataset.sfil) { fil = b.dataset.sfil; el.querySelectorAll("[data-sfil]").forEach((x) => x.setAttribute("aria-pressed", x === b)); draw(); }
        else if (b.dataset.ssort) { const k = b.dataset.ssort; dir = sortKey === k ? -dir : (k === "symbol" ? 1 : -1); sortKey = k; draw(); }
        else scan();
      });
      scan();
      every(300000, scan);
    },

    async account(el) {
      if (!TA.Auth.available()) { el.innerHTML = `<section class="card">${state("off", "Accounts need the TRADE-AI server", "Set <code>api.backendBaseUrl</code> in <code>config.js</code>.")}</section>`; return; }
      const user = await TA.Auth.me();
      if (!el.isConnected) return;
      if (user) {
        const u = user.usage;
        el.innerHTML = `<div class="grid-dash"><section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("user")}Your account</h2><span class="badge">${u.plan !== "trial" ? "Pro" : u.pro ? "Pro trial" : "Free"}</span></div>
          <dl class="detail-grid" style="grid-template-columns:1fr 1fr;margin:0 0 16px">
            <div class="level" style="grid-column:1/-1"><dt>Email</dt><dd style="font-family:var(--font-sans)">${TA.esc(user.email)}</dd></div>
            <div class="level"><dt>Plan</dt><dd style="font-family:var(--font-sans)">${u.plan !== "trial" ? "Pro (paid)" : u.pro ? `Pro trial · ${u.trial_days_left} day${u.trial_days_left === 1 ? "" : "s"} left` : "Free"}</dd></div>
            <div class="level"><dt>Member since</dt><dd style="font-family:var(--font-sans)">${TA.fmtTime(user.created_at)}</dd></div></dl>
          <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" id="signout">${TA.icon("logout", "icon-sm")}Sign out</button>${user.is_admin ? `<a class="btn" href="#/stats">${TA.icon("chart", "icon-sm")}Usage stats</a>` : ""}</div></section>
          <section class="card panel span-6"><h2 style="font-size:1rem">${TA.icon("shield")}Change password</h2>
            <form class="auth-form" id="pwForm" novalidate>
              <div class="field"><label for="pw0">Current password</label><input id="pw0" type="password" autocomplete="current-password" /></div>
              <div class="field"><label for="pw1">New password</label><input id="pw1" type="password" minlength="8" autocomplete="new-password" /><span class="hint">At least 8 characters.</span></div>
              <span class="err" id="pwErr" role="alert"></span><button class="btn btn-sm" type="submit">Update password</button></form></section>
          <section class="card panel span-6"><h2 style="font-size:1rem">${TA.icon("x")}Delete account</h2>
            <p class="muted" style="font-size:.86rem;margin:0 0 10px">Removes your account and its settings. This can't be undone.</p>
            <form class="auth-form" id="delForm" novalidate>
              <div class="field"><label for="pwd">Confirm with your password</label><input id="pwd" type="password" autocomplete="current-password" /></div>
              <span class="err" id="delErr" role="alert"></span><button class="btn btn-sm" type="submit">Delete my account</button></form></section>
          <section class="card panel span-6"><h2 style="font-size:1rem">${TA.icon("info")}Free vs Pro</h2>
          <ul style="margin:0;padding-left:18px;font-size:.88rem;color:var(--tx-2);display:grid;gap:4px">
            <li>Free for everyone: dashboard, live charts, signals with full levels, signal history, risk tools and alerts.</li>
            <li>Pro adds the Market risk monitor, Market scanner, Futures intelligence and Pattern &amp; SMC analysis. New accounts get ${C.pricing.trialDays} days of Pro free.</li>
            <li>Signals are experimental analysis, not advice. TRADE-AI never places trades.</li></ul>
          <p style="margin:12px 0 0;font-size:.84rem"><a href="legal/terms.html">Terms</a> · <a href="legal/privacy.html">Privacy</a> · <a href="legal/risk.html">Risk disclaimer</a></p></section></div>`;
        $("#signout", el).addEventListener("click", () => { TA.Auth.signOut(); TA.toast("Signed out.", "info"); location.hash = "#/login"; });
        $("#pwForm", el).addEventListener("submit", async (e) => {
          e.preventDefault();
          const r = await TA.Auth.post("/api/auth/password", { current_password: $("#pw0", el).value, new_password: $("#pw1", el).value });
          if (!r.ok) { $("#pwErr", el).textContent = r.error; return; }
          e.target.reset(); $("#pwErr", el).textContent = ""; TA.toast("Password updated.", "success");
        });
        $("#delForm", el).addEventListener("submit", async (e) => {
          e.preventDefault();
          const r = await TA.Auth.post("/api/auth/delete", { password: $("#pwd", el).value });
          if (!r.ok) { $("#delErr", el).textContent = r.error; return; }
          TA.Auth.signOut(); TA.toast("Your account was deleted.", "info"); location.hash = "#/dashboard";
        });
        return;
      }
      let mode = authMode || "login"; authMode = null;
      const feats = await TA.Auth.features();
      if (!el.isConnected) return;
      const draw = () => {
        el.innerHTML = `<section class="card panel" style="max-width:520px"><div class="panel-head"><h2>${TA.icon("user")}${mode === "login" ? "Sign in" : "Create your free account"}</h2></div>
          <p class="muted" style="margin:0 0 14px;font-size:.88rem">${mode === "login" ? "Sign in to your TRADE-AI account." : `Free account with ${C.pricing.trialDays} days of Pro (scanner, futures, SMC). No card needed.`}</p>
          <form class="auth-form" id="authForm" novalidate>
            <div class="field"><label for="em">Email</label><input id="em" type="email" autocomplete="email" required /></div>
            <div class="field"><label for="pw">Password</label><input id="pw" type="password" minlength="8" autocomplete="${mode === "login" ? "current-password" : "new-password"}" required /><span class="hint">At least 8 characters.</span></div>
            <span class="err" id="authErr" role="alert"></span>
            ${mode === "register" ? `<p class="muted" style="margin:0;font-size:.8rem">By creating an account you agree to the <a href="legal/terms.html" target="_blank" rel="noopener">Terms</a> and <a href="legal/privacy.html" target="_blank" rel="noopener">Privacy Policy</a>, and confirm you've read the <a href="legal/risk.html" target="_blank" rel="noopener">Risk disclaimer</a>. You must be 18 or over.</p>` : ""}
            <button class="btn btn-primary" type="submit">${mode === "login" ? "Sign in" : "Create account"}</button>
          </form>
          <p style="margin:14px 0 0;font-size:.88rem">${mode === "login" ? "No account yet?" : "Already have one?"} <a href="#" id="swap">${mode === "login" ? "Create one" : "Sign in"}</a>${mode === "login" && feats.password_reset ? ` · <a href="#" id="forgot">Forgot password?</a>` : ""}</p></section>`;
        $("#swap", el).addEventListener("click", (e) => { e.preventDefault(); mode = mode === "login" ? "register" : "login"; draw(); });
        const fg = $("#forgot", el);
        if (fg) fg.addEventListener("click", async (e) => {
          e.preventDefault();
          const email = $("#em", el).value.trim();
          if (!email) { $("#authErr", el).textContent = "Type your email above first, then click Forgot password."; return; }
          const r = await TA.Auth.forgot(email);
          $("#authErr", el).textContent = "";
          TA.toast(r.ok ? r.message : r.error, r.ok ? "success" : "error");
        });
        $("#authForm", el).addEventListener("submit", async (e) => {
          e.preventDefault();
          const btn = e.target.querySelector("button"); btn.disabled = true;
          const r = await TA.Auth.submit(mode, $("#em", el).value.trim(), $("#pw", el).value);
          btn.disabled = false;
          if (!r.ok) { $("#authErr", el).textContent = r.error; return; }
          TA.toast(mode === "login" ? "Signed in." : `Account created. Your ${C.pricing.trialDays}-day Pro trial has started.`, "success");
          const back = sessionStorage.getItem("ta-after-auth");
          location.hash = back && !/^#\/(login|signup|account|reset)/.test(back) ? back : "#/dashboard";
          sessionStorage.removeItem("ta-after-auth");
        });
      };
      draw();
    },

    async billing(el) {
      const P = C.pricing;
      const user = TA.Auth.available() ? await TA.Auth.me() : null;
      if (!el.isConnected) return;
      const sub = user && user.subscription, paid = user && user.usage.plan !== "trial";
      const link = user && TA.Auth.checkoutLink();
      const action = !user ? `<a class="btn btn-primary" href="#/account">Sign in to upgrade</a>`
        : paid ? (sub && sub.portal_url ? `<a class="btn" href="${TA.esc(sub.portal_url)}" target="_blank" rel="noopener">Manage subscription</a>` : "")
        : link ? `<a class="btn btn-primary" href="${TA.esc(link)}" target="_blank" rel="noopener">Upgrade · $${P.monthlyPrice}/month</a>`
        : `<button class="btn btn-primary" aria-disabled="true" id="upg">Upgrade</button>`;
      const subLine = sub ? `<div class="level" style="grid-column:1/-1"><dt>Subscription</dt><dd style="font-family:var(--font-sans)">${TA.esc(sub.status)}${sub.ends_at ? ` · ends ${TA.fmtTime(sub.ends_at)}` : sub.renews_at ? ` · renews ${TA.fmtTime(sub.renews_at)}` : ""}</dd></div>` : "";
      el.innerHTML = `<div class="grid-dash"><section class="card panel span-6"><div class="panel-head"><h2>${TA.icon("card")}Plan</h2><span class="badge">${paid ? "Pro" : "Trial"}</span></div>
        <p style="font-size:1.6rem;font-family:var(--font-display);color:var(--tx-1);margin:0">$${P.monthlyPrice} <span class="muted" style="font-size:.9rem">USD / month${paid ? "" : " after trial"}</span></p>
        <dl class="detail-grid" style="grid-template-columns:1fr 1fr;margin:16px 0">
          <div class="level"><dt>Free trial</dt><dd style="font-family:var(--font-sans)">${user && !paid ? (user.usage.pro ? `${user.usage.trial_days_left} day${user.usage.trial_days_left === 1 ? "" : "s"} left` : "Ended") : `${P.trialDays} days of Pro`}</dd></div>
          <div class="level"><dt>Pro includes</dt><dd style="font-family:var(--font-sans)">Scanner, futures data, SMC analysis</dd></div>
          ${subLine}</dl>${action}</section>
        <section class="card panel span-6">${link || paid ? `<h2 style="font-size:1rem">${TA.icon("shield")}Payments</h2><p class="muted" style="font-size:.88rem;margin:0">Checkout and card details are handled by Lemon Squeezy, our payment provider. TRADE-AI never sees or stores card numbers. Your plan updates here a few seconds after payment. Cancel anytime from "Manage subscription".</p>`
          : state("off", "Checkout isn't open yet", "Payments will be handled by Lemon Squeezy. Until checkout opens, every new account gets a free Pro trial.")}</section></div>`;
      const u = $("#upg", el); if (u) u.addEventListener("click", () => TA.toast("Checkout isn't available yet.", "info"));
      if (user && !paid && link) every(15000, async () => { const m = await TA.Auth.me(); if (m && m.usage.plan !== "trial") { TA.toast("Payment received. Pro is active.", "success"); route(); } });
    }
  };

  const soonCopy = {
  };
  Object.keys(soonCopy).forEach((id) => (views[id] = (el) => {
    const [t, d] = soonCopy[id];
    el.innerHTML = `<section class="card">${state("soon", `${t} — not available yet`, d, `<a class="btn btn-sm" href="#/dashboard">Back to dashboard</a>`)}</section>`;
  }));

  // ---------- Router ----------
  let current;
  // Sign-in wall: when accounts are available, nothing but the sign-in/register/reset pages opens without a session.
  let authMode = null;
  const OPEN_ROUTES = ["account", "login", "signup", "reset"];
  function route() {
    closeLive();
    let id = (location.hash.match(/^#\/([\w-]+)/) || [])[1] || "dashboard";
    const walled = TA.Auth.available() && !TA.Auth.signedIn();
    document.body.classList.toggle("auth-wall", walled);
    if (walled && !OPEN_ROUTES.includes(id)) {
      try { sessionStorage.setItem("ta-after-auth", location.hash || "#/dashboard"); } catch {}
      history.replaceState(null, "", location.pathname + location.search + "#/login");
      id = "login";
    }
    if (id === "login" || id === "signup") { authMode = id === "signup" ? "register" : "login"; id = "account"; }
    const r = byId[id] || byId.dashboard;
    current = r.id;
    document.querySelectorAll("[data-route]").forEach((a) => a.dataset.route === r.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    const wallNow = document.body.classList.contains("auth-wall");
    $("#viewTitle").innerHTML = wallNow ? `<a href="index.html" style="color:inherit;text-decoration:none;font-weight:800">TRADE<span style="color:#36D6E7">-AI</span></a>` : TA.esc(r.label);
    document.title = wallNow ? `${authMode === "register" ? "Create account" : "Sign in"} · TRADE-AI` : `${r.label} · TRADE-AI`;
    if (TA.track && r.id !== "stats" && r.id !== "reset") TA.track("/app/" + r.id);
    const host = $("#content");
    const view = document.createElement("div");
    view.className = "view"; view.style.display = "grid"; view.style.gap = "16px";
    host.replaceChildren(view);
    views[r.id](view);
    drawer(false);
  }
  // Top banner inviting the user to turn on browser notifications (hidden once on, unsupported, blocked or dismissed).
  async function notifBanner() {
    const nb = $("#notifBanner");
    if (!nb || !TA.Auth.available() || !TA.Auth.signedIn() || !TA.Delivery || !TA.Delivery.pushSupported()) return;
    let dismissed = false; try { dismissed = localStorage.getItem("ta-nb-dismissed") === "1"; } catch {}
    if (dismissed || (await TA.Delivery.current().catch(() => null))) { nb.hidden = true; return; }
    const info = await TA.Delivery.info();
    if (!info.push_public_key) return;
    const blocked = Notification.permission === "denied";
    nb.innerHTML = `<span class="nb-ic">${TA.icon("bell")}</span>
      <span class="nb-text"><b>${blocked ? "Notifications are blocked for TRADE-AI" : "Get notified about new setups"}</b><small>${blocked
        ? "To get alerts for new setups, click the lock or settings icon next to the address bar, set Notifications to Allow, then reload."
        : "A notification when a new LONG or SHORT appears, even with the site closed. Analysis only."}</small></span>
      ${blocked ? "" : `<button class="btn btn-primary btn-sm" id="nbOn">Turn on notifications</button>`}
      <button class="nb-x" id="nbX" aria-label="Dismiss">${TA.icon("x", "icon-sm")}</button>`;
    nb.hidden = false;
    $("#nbX").addEventListener("click", () => { try { localStorage.setItem("ta-nb-dismissed", "1"); } catch {} nb.hidden = true; });
    if (!blocked) $("#nbOn").addEventListener("click", async (e) => {
      e.target.disabled = true;
      const r = await TA.Delivery.enablePush(info.push_public_key).catch((err) => ({ ok: false, error: err.message }));
      TA.toast(r.ok ? "Notifications on. You'll hear about new setups." : r.error, r.ok ? "success" : "error");
      if (r.ok || Notification.permission === "denied") nb.hidden = true; else e.target.disabled = false;
      if (current === "alerts") route();
    });
  }
  setTimeout(notifBanner, 1500);

  document.addEventListener("ta:auth", () => { if (!TA.Auth.signedIn()) route(); });

  window.addEventListener("hashchange", () => { route(); $("#content").focus({ preventScroll: true }); window.scrollTo(0, 0); });

  // ---------- Delegated actions ----------
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-unlock],[data-act],[data-tf],[data-ind],[data-sig]");
    if (!t) return;
    if (t.dataset.act === "demo-on") { demoToggle.checked = true; store.demo = true; renderConn(); route(); }
    else if (t.dataset.act === "retry") route();
    else if (t.dataset.tf || t.dataset.ind) {
      const panel = t.closest(".chart-wrap") || t.closest("[data-chart]");
      if (t.dataset.tf) { ui.tf = t.dataset.tf; panel.querySelectorAll("[data-tf]").forEach((b) => b.setAttribute("aria-pressed", b === t)); }
      else { ui[t.dataset.ind] = !ui[t.dataset.ind]; t.setAttribute("aria-pressed", ui[t.dataset.ind]); if (panel._redraw) { panel._redraw(); return; } }
      loadChart(panel);
    } else if (t.dataset.unlock) {
      e.stopPropagation();
      const id = t.dataset.unlock;
      if (!TA.Auth.signedIn()) { TA.modal.close && TA.modal.close(); sessionStorage.setItem("ta-after-auth", location.hash); location.hash = "#/account"; return; }
      t.disabled = true;
      TA.Signals.unlock(id).then((r) => {
        t.disabled = false;
        if (r.needsAuth) { sessionStorage.setItem("ta-after-auth", location.hash); location.hash = "#/account"; return; }
        if (!r.ok) { TA.toast(r.status === 402 ? "Your free trial signals are used up. Subscriptions aren't available yet." : `Couldn't unlock: ${r.error}`, "error"); return; }
        const i = lastSignals.findIndex((x) => x.id === id);
        if (i >= 0) lastSignals[i] = r.signal;
        TA.toast("Unlocked.", "success");
        if (document.querySelector(".modal-body .detail")) TA.modal.open(TA.signalDetail(r.signal));
        route();
      });
    } else if (t.dataset.sig) {
      const s = lastSignals.find((x) => x.id === t.dataset.sig);
      if (s) {
        TA.modal.open(TA.signalDetail(s));
        if (s.source === "live") TA.Signals.getEvents(s.id).then((r) => {
          const body = document.querySelector(".modal-body .detail"); if (!body || r.status !== "ok") return;
          const ev = r.data.events, oc = r.data.outcome;
          const nice = { triggered: "Entry triggered", tp1_hit: "Target 1 hit", tp2_hit: "Target 2 hit", tp3_hit: "Target 3 hit", stopped: "Stopped", expired: "Expired", invalidated: "Invalidated" };
          body.insertAdjacentHTML("beforeend", `<div><h3>Lifecycle events</h3>${ev.length ? `<ol style="margin:0;padding-left:18px;font-size:.88rem;color:var(--tx-2)">${ev.map((e) => `<li><b>${nice[e.type] || e.type}</b> at ${TA.fmtPrice(e.price)} · ${TA.fmtTime(e.at)}${e.detail && e.detail.ambiguous_same_candle ? ' <span class="badge">stop and target in the same candle — stop assumed</span>' : ""}</li>`).join("")}</ol>` : '<p class="muted" style="font-size:.86rem;margin:0">Waiting for price to reach the entry zone.</p>'}
            ${oc ? `<p style="font-size:.86rem;margin:10px 0 0">Simulated result: <b class="${oc.net_r >= 0 ? "up" : "down"}">${oc.net_r >= 0 ? "+" : ""}${oc.net_r.toFixed(2)}R</b> after costs (${oc.targets_hit} target${oc.targets_hit === 1 ? "" : "s"} hit, exit: ${oc.exit}). <span class="muted">Model: ${TA.esc(oc.model)}. A single signal's result says nothing about future results.</span></p>` : ""}</div>`);
        });
      }
    }
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-sym]")) { ui.sym = +e.target.value; loadChart(e.target.closest(".chart-wrap") || e.target.closest("[data-chart]")); }
  });
  document.addEventListener("keydown", (e) => {
    const t = e.target.closest && e.target.closest('[data-sig][role="button"]');
    if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); t.click(); }
  });

  // ---------- Backend API status ----------
  async function renderApi() {
    const el = $("#apiStatus"), r = await TA.Health.check();
    const map = {
      not_configured: ["var(--tx-3)", "plug", "API: not configured"],
      ok: ["var(--up)", "check", "API: healthy"],
      degraded: ["var(--down)", "alert", "API: degraded (database)"],
      unreachable: ["var(--down)", "wifiOff", "API: unreachable"]
    };
    const [col, ic, label] = map[r.status];
    el.innerHTML = `<span style="color:${col};display:inline-flex">${TA.icon(ic, "icon-sm")}</span><span>${label}</span>`;
    el.title = r.checkedAt ? `Checked ${TA.fmtTime(r.checkedAt)}` : "";
  }

  // ---------- Alert badge (new alerts since last visit to the Alerts page) ----------
  async function renderAlertBadge() {
    const link = document.querySelector('.side-link[data-route="alerts"]'); if (!link) return;
    let b = link.querySelector(".soon"); const r = await TA.Signals.getAlerts(+(localStorage.getItem("ta-alert-seen") || 0));
    if (r.status !== "ok" || !r.data.length) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement("span"); b.className = "soon"; link.appendChild(b); }
    b.textContent = r.data.length > 99 ? "99+" : String(r.data.length); b.style.color = "var(--accent)"; b.setAttribute("aria-label", `${r.data.length} new alerts`);
  }
  if (TA.Signals.isConfigured()) { renderAlertBadge(); setInterval(() => { if (!document.hidden) renderAlertBadge(); }, 60000); }

  // ---------- Timezone preference (display only; stored in this browser) ----------
  const tzSel = $("#tzSel");
  tzSel.innerHTML = `<option value="local">Local — ${TA.esc(TA.localTz())}</option>` + TA.timezones().map((z) => `<option value="${z}">${z.replace(/_/g, " ")}</option>`).join("");
  tzSel.value = TA.getTz();
  if (tzSel.value !== TA.getTz()) tzSel.value = "local";
  tzSel.addEventListener("change", () => { TA.setTz(tzSel.value); TA.toast(`Times now shown in ${TA.activeTz().replace(/_/g, " ")}`, "clock"); route(); });

  renderConn();
  renderApi();
  route();
})();
