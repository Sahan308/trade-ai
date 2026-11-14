/* Reusable UI components (pure render functions → HTML strings). */
(function () {
  const TA = window.TA;
  const lifeLabel = { active: "Active", triggered: "Triggered", target_reached: "Target reached", stopped: "Stopped", expired: "Expired", invalidated: "Invalidated" };
  TA.lifeLabel = lifeLabel;

  const scoreTip = "Heuristic setup score (0–100) summarising how many conditions align. It is NOT a probability of winning.";

  TA.signalCard = (s) => {
    const isDemo = s.source === "demo";
    const lv = (k, v) => `<div class="level"><dt>${k}</dt><dd>${v}</dd></div>`;
    const levels = s.entry
      ? `<dl class="signal-levels">
          ${lv("Entry zone", `${TA.fmtPrice(s.entry[0])} – ${TA.fmtPrice(s.entry[1])}`)}
          ${lv("Stop", TA.fmtPrice(s.stop))}
          ${lv("Target 1", TA.fmtPrice(s.targets[0]))}
          ${lv("Target 2", TA.fmtPrice(s.targets[1]))}
        </dl>`
      : `<p class="muted" style="margin:0;font-size:.88rem">No entry — conditions don't support a trade right now.</p>`;
    return `
      <article class="card card-hover signal" aria-label="${TA.esc(s.symbol)} ${s.direction} setup${isDemo ? ", illustrative example" : ""}">
        ${isDemo ? `<div class="demo-stamp">${TA.icon("flask", "icon-sm")} Illustrative example</div>` : ""}
        <div class="signal-head">
          <div>
            <div class="signal-sym">${TA.esc(s.symbol)}</div>
            <div class="signal-meta">${s.market} · ${TA.esc(s.strategy)} · ${s.timeframe}</div>
          </div>
          ${TA.dirBadge(s.direction)}
        </div>
        ${levels}
        <div class="score">
          <span class="term" tabindex="0" data-tip="${scoreTip}">Setup score</span>
          <div class="score-bar" role="img" aria-label="Heuristic score ${s.score} of 100"><span style="width:${s.score}%"></span></div>
          <span class="num">${s.score}</span>
        </div>
        <ul class="evidence">
          ${s.supporting.slice(0, 2).map((t) => `<li><span class="up">${TA.icon("check", "icon-sm")}</span><span><span class="sr-only">Supporting: </span>${TA.esc(t)}</span></li>`).join("")}
          ${s.conflicting.slice(0, 1).map((t) => `<li><span class="down">${TA.icon("x", "icon-sm")}</span><span><span class="sr-only">Conflicting: </span>${TA.esc(t)}</span></li>`).join("")}
        </ul>
      </article>`;
  };

  TA.signalDetail = (s) => {
    const isDemo = s.source === "demo";
    const cell = (k, v) => `<div class="level"><dt>${k}</dt><dd>${v}</dd></div>`;
    return `
      <div class="detail">
        <div>
          ${isDemo ? `<span class="badge badge-demo">${TA.icon("flask", "icon-sm")}Illustrative example</span>` : ""}
          <div style="display:flex;gap:12px;align-items:center;margin-top:12px;flex-wrap:wrap">
            <h2 id="modal-title" style="margin:0">${TA.esc(s.symbol)}</h2>${TA.dirBadge(s.direction)}
            <span class="badge">${s.market}</span><span class="badge">${s.timeframe}</span>
          </div>
          <p class="muted" style="margin:8px 0 0;font-size:.88rem">${TA.esc(s.strategy)} · Generated ${TA.fmtTime(s.createdAt)} · Source: ${TA.esc(s.dataSource)} · Data age at render: ${TA.ago(s.createdAt)}</p>
        </div>

        <div>
          <h3 style="font-size:.85rem;color:var(--tx-3);text-transform:uppercase;letter-spacing:.06em">Lifecycle</h3>
          <div class="lifecycle" role="list">${TA.Signals.LIFECYCLE.map((l) => `<span role="listitem" class="${l === s.lifecycle ? "on" : ""}" ${l === s.lifecycle ? 'aria-current="step"' : ""}>${lifeLabel[l]}</span>`).join("")}</div>
        </div>

        <dl class="detail-grid" style="margin:0">
          ${cell("Entry zone", s.entry ? `${TA.fmtPrice(s.entry[0])} – ${TA.fmtPrice(s.entry[1])}` : "—")}
          ${cell("Stop-loss", TA.fmtPrice(s.stop))}
          ${cell("Target 1", TA.fmtPrice(s.targets[0]))}
          ${cell("Target 2", TA.fmtPrice(s.targets[1]))}
        </dl>
        <div class="level"><dt><span class="term" tabindex="0" data-tip="The condition that proves the idea wrong. If it happens, the setup is void even before the stop is hit.">Invalidation</span></dt><dd style="font-family:var(--font-sans)">${TA.esc(s.invalidation)}</dd></div>

        <div class="score"><span class="term" tabindex="0" data-tip="${scoreTip}">Heuristic setup score</span>
          <div class="score-bar" role="img" aria-label="Heuristic score ${s.score} of 100"><span style="width:${s.score}%"></span></div><span class="num">${s.score}/100</span></div>
        <p class="muted" style="margin:-10px 0 0;font-size:.8rem">Not a win probability. Scores have not been validated against outcomes.</p>

        <div class="split">
          <div><h3>Supporting evidence</h3><ul class="evidence">${s.supporting.map((t) => `<li><span class="up">${TA.icon("check", "icon-sm")}</span>${TA.esc(t)}</li>`).join("")}</ul></div>
          <div><h3>Conflicting evidence</h3><ul class="evidence">${s.conflicting.map((t) => `<li><span class="down">${TA.icon("x", "icon-sm")}</span>${TA.esc(t)}</li>`).join("")}</ul></div>
        </div>

        <div class="split">
          <div class="measured"><h3 style="font-size:.95rem;display:flex;gap:6px;align-items:center">${TA.icon("database", "icon-sm")} Measured performance</h3>
            <p style="font-size:.86rem;margin:0">No tracked outcomes yet. Historical results appear here only once signals are recorded and resolved by the backend.</p></div>
          <div class="estimate"><h3 style="font-size:.95rem;display:flex;gap:6px;align-items:center">${TA.icon("flask", "icon-sm")} Unvalidated estimates</h3>
            <p style="font-size:.86rem;margin:0">The setup score above is a model heuristic, not a measured result.</p></div>
        </div>
        <p class="muted" style="font-size:.78rem;margin:0">Analysis only. TRADE-AI never places trades. Crypto markets are volatile — you can lose money.</p>
      </div>`;
  };

  // Candlestick SVG with optional EMA + volume. Pure function of the candles passed in.
  // range: optional fixed [lo, hi] price scale so live redraws don't rescale/jump.
  TA.candleChart = (cs, { w = 800, h = 320, ema = true, volume = true, grid = true, cls = "", range = null } = {}) => {
    if (!cs || !cs.length) return "";
    const padR = 54, padB = 22, volH = volume ? 46 : 0;
    const [lo, hi] = range || [Math.min(...cs.map((c) => c.l)), Math.max(...cs.map((c) => c.h))];
    const ch = h - padB - volH - 10;
    const y = (v) => 8 + ((hi - v) / (hi - lo)) * (ch - 8);
    const step = (w - padR) / cs.length, bw = Math.max(2, step * 0.6);
    const vmax = Math.max(...cs.map((c) => c.v));
    let out = "";
    if (grid) for (let i = 0; i <= 4; i++) {
      const v = lo + ((hi - lo) * i) / 4, yy = y(v);
      out += `<line class="gl" x1="0" x2="${w - padR}" y1="${yy}" y2="${yy}"/><text class="ax" x="${w - padR + 6}" y="${yy + 3}">${v >= 1000 ? v.toFixed(0) : v >= 10 ? v.toFixed(2) : v.toFixed(4)}</text>`;
    }
    cs.forEach((c, i) => {
      const x = i * step + step / 2, up = c.c >= c.o, col = up ? "var(--up)" : "var(--down)";
      out += `<g class="candle${i === cs.length - 1 ? " candle-last" : ""}" style="--i:${i}"><line x1="${x}" x2="${x}" y1="${y(c.h)}" y2="${y(c.l)}" stroke="${col}" stroke-width="1"/>
        <rect x="${x - bw / 2}" y="${y(Math.max(c.o, c.c))}" width="${bw}" height="${Math.max(1, Math.abs(y(c.o) - y(c.c)))}" fill="${col}" rx="1" opacity="${up ? 0.9 : 0.85}"/></g>`;
      if (volume) out += `<rect class="vol" style="--i:${i}" x="${x - bw / 2}" y="${h - padB - (c.v / vmax) * volH}" width="${bw}" height="${(c.v / vmax) * volH}" fill="${col}" opacity="0.22"/>`;
    });
    if (ema) {
      let e = cs[0].c; const k = 2 / 21;
      const pts = cs.map((c, i) => { e = c.c * k + e * (1 - k); return `${(i * step + step / 2).toFixed(1)},${y(e).toFixed(1)}`; });
      out += `<polyline class="draw" style="--len:2400" points="${pts.join(" ")}" fill="none" stroke="var(--accent)" stroke-width="1.6" stroke-linejoin="round"/>`;
      const last = pts[pts.length - 1].split(",");
      out += `<circle class="ema-dot" cx="${last[0]}" cy="${last[1]}" r="3" fill="var(--accent)"/>`;
    }
    return `<svg class="${cls}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Candlestick chart${ema ? " with 20-period EMA" : ""}">${out}</svg>`;
  };
})();
