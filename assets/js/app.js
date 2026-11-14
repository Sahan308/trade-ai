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
  const ui = { tf: "1H", ema: true, volume: true, sym: 0, sma50: false, bb: false, vwap: false, st: false, psar: false, ichi: false, pat: true };
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
           ["ichi", "Ichimoku cloud", "Area between Ichimoku spans A and B (no look-ahead)."], ["pat", "Patterns", "Markers for candlestick patterns: context, not predictions."]]
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
      const markers = ui.pat ? a.patterns.filter((p) => p.index >= off).map((p) => ({ index: p.index - off, bias: p.bias, label: `${p.pattern} (${p.bias})` })) : [];
      area.innerHTML = TA.candleChart(cs.slice(-VIEW), { w: 900, h: 340, ema: ui.ema, volume: ui.volume, overlays, bands, dots, markers });
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
      patterns: A.detectCandlestickPatterns(o, h, l, c), formations: A.doubleTopsBottoms(h, l, c)
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
      <h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:18px 0 8px">Candlestick patterns · last 30 candles</h3>
      ${recent.length ? `<ul class="list-signals" style="list-style:none;margin:0;padding:0">${recent.map((p) => `<li class="sig-row" style="cursor:default">${biasBadge(p.bias)}<span><b>${p.pattern}</b><br/><span class="muted" style="font-size:.8rem">${p.candles.length} candle${p.candles.length > 1 ? "s" : ""} · ${TA.fmtTime(a.t[p.index])}</span></span><span class="muted" style="font-size:.78rem">${((n) => (n === 0 ? "current candle" : n === 1 ? "1 bar ago" : `${n} bars ago`))(cs.length - 1 - p.index)}</span></li>`).join("")}</ul>`
        : `<p class="muted" style="font-size:.86rem">No patterns in the last 30 candles.</p>`}
      <h3 style="font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--tx-3);margin:18px 0 8px">Chart formations</h3>
      ${a.formations.length ? `<ul style="margin:0;padding-left:18px;font-size:.88rem;color:var(--tx-2)">${a.formations.slice(-5).map((f) => `<li>${f.formation} · neckline ${fmtN(f.neckline)} · <b>${f.status}</b> · peaks ${TA.fmtTime(a.t[f.points[0]])} and ${TA.fmtTime(a.t[f.points[2]])}</li>`).join("")}</ul>`
        : `<p class="muted" style="font-size:.86rem">No double tops or bottoms in view.</p>`}
      <p class="muted" style="font-size:.76rem;margin:14px 0 0">The current candle is still forming, so its patterns and readings can change until it closes. Formulas: see the project README and <code>backend/app/analysis</code>.</p>`;
  }

  // ---------- Views ----------
  const views = {
    async dashboard(el) {
      el.innerHTML = `
        <div class="status-row">
          <div class="card stat"><small>Market status</small><strong id="mkStatus">${store.demo ? "Sample" : TA.MarketData.isConfigured() ? "Open 24/7" : "Unknown"}</strong><p class="muted">${store.demo ? "Preview fixture" : TA.MarketData.isConfigured() ? "Crypto trades continuously" : "Needs data feed"}</p></div>
          <div class="card stat"><small>Data connection</small><strong>${store.demo ? `<span class="dot" style="color:var(--accent)"></span>Sample` : TA.MarketData.isConfigured() ? `<span class="dot dot-live" style="color:var(--teal)"></span>Live` : `${TA.icon("wifiOff", "icon-sm")}Offline`}</strong><p class="muted">${TA.esc(TA.MarketData.describeSource(store.demo))}</p></div>
          <div class="card stat"><small>Data freshness</small><strong id="fresh">—</strong><p class="muted">Watchlist · stale after ${C.api.staleAfterSeconds}s</p></div>
          <div class="card stat"><small>Trial signals</small><strong id="usageTxt"><span class="skeleton" style="width:60px;display:inline-block">&nbsp;</span></strong><div class="usage" id="usageBar" aria-hidden="true"></div></div>
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
      const u = use.data;
      $("#usageTxt", el).innerHTML = u.used == null ? `— <span class="muted" style="font-size:.85rem">of ${u.limit}</span>` : `${u.used} <span class="muted" style="font-size:.85rem">of ${u.limit} used${use.source === "demo" ? " (sample)" : ""}</span>`;
      $("#usageBar", el).innerHTML = Array.from({ length: u.limit }, (_, i) => `<i class="${u.used != null && i < u.used ? "used" : ""}"></i>`).join("");
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

    chart(el) { el.innerHTML = `<div class="chart-wrap">${chartPanel("Advanced chart", { withReadings: true })}</div>`; loadChart(el.querySelector(".chart-wrap")); },

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
    closeLive();
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
      const panel = t.closest(".chart-wrap") || t.closest("[data-chart]");
      if (t.dataset.tf) { ui.tf = t.dataset.tf; panel.querySelectorAll("[data-tf]").forEach((b) => b.setAttribute("aria-pressed", b === t)); }
      else { ui[t.dataset.ind] = !ui[t.dataset.ind]; t.setAttribute("aria-pressed", ui[t.dataset.ind]); if (panel._redraw) { panel._redraw(); return; } }
      loadChart(panel);
    } else if (t.dataset.sig) {
      const s = lastSignals.find((x) => x.id === t.dataset.sig);
      if (s) TA.modal.open(TA.signalDetail(s));
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
