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

  // Candlestick SVG with optional EMA, volume and analysis overlays. Pure function of its inputs.
  // overlays: [{ values, color, width?, dash?, label }]  — arrays aligned with cs (null = gap)
  // bands:    [{ upper, lower, color }]                  — filled area between two aligned arrays
  // dots:     [{ values, color }]                        — e.g. Parabolic SAR
  // markers:  [{ index, bias, label }]                   — pattern markers (▲ bullish, ▼ bearish, ◆ neutral)
  TA.candleChart = (cs, { w = 800, h = 320, ema = true, volume = true, grid = true, cls = "", range = null, overlays = [], bands = [], dots = [], markers = [] } = {}) => {
    if (!cs || !cs.length) return "";
    const padR = 54, padB = 22, volH = volume ? 46 : 0;
    let lo, hi;
    if (range) [lo, hi] = range;
    else {
      lo = Math.min(...cs.map((c) => c.l)); hi = Math.max(...cs.map((c) => c.h));
      const extra = [...overlays.map((o) => o.values), ...bands.flatMap((b) => [b.upper, b.lower]), ...dots.map((d) => d.values)];
      extra.forEach((arr) => arr.forEach((v) => { if (v != null && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }));
    }
    const ch = h - padB - volH - 10;
    const y = (v) => 8 + ((hi - v) / (hi - lo || 1)) * (ch - 8);
    const step = (w - padR) / cs.length, bw = Math.max(2, step * 0.6);
    const xAt = (i) => i * step + step / 2;
    const vmax = Math.max(...cs.map((c) => c.v)) || 1;
    const path = (arr) => {
      let d = "", pen = false;
      arr.forEach((v, i) => { if (v == null || !Number.isFinite(v)) { pen = false; return; } d += `${pen ? "L" : "M"}${xAt(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
      return d;
    };
    let out = "";
    if (grid) for (let i = 0; i <= 4; i++) {
      const v = lo + ((hi - lo) * i) / 4, yy = y(v);
      out += `<line class="gl" x1="0" x2="${w - padR}" y1="${yy}" y2="${yy}"/><text class="ax" x="${w - padR + 6}" y="${yy + 3}">${v >= 1000 ? v.toFixed(0) : v >= 10 ? v.toFixed(2) : v.toFixed(4)}</text>`;
    }
    bands.forEach((b) => {
      // one polygon per contiguous run where both edges exist
      let run = [];
      const flush = () => {
        if (run.length > 1) out += `<polygon points="${run.map((i) => `${xAt(i).toFixed(1)},${y(b.upper[i]).toFixed(1)}`).concat(run.slice().reverse().map((i) => `${xAt(i).toFixed(1)},${y(b.lower[i]).toFixed(1)}`)).join(" ")}" fill="${b.color}" opacity="${b.opacity ?? 0.1}" stroke="none"/>`;
        run = [];
      };
      cs.forEach((_, i) => { if (b.upper[i] != null && b.lower[i] != null) run.push(i); else flush(); });
      flush();
    });
    cs.forEach((c, i) => {
      const x = xAt(i), up = c.c >= c.o, col = up ? "var(--up)" : "var(--down)";
      out += `<g class="candle${i === cs.length - 1 ? " candle-last" : ""}" style="--i:${i}"><line x1="${x}" x2="${x}" y1="${y(c.h)}" y2="${y(c.l)}" stroke="${col}" stroke-width="1"/>
        <rect x="${x - bw / 2}" y="${y(Math.max(c.o, c.c))}" width="${bw}" height="${Math.max(1, Math.abs(y(c.o) - y(c.c)))}" fill="${col}" rx="1" opacity="${up ? 0.9 : 0.85}"/></g>`;
      if (volume) out += `<rect class="vol" style="--i:${i}" x="${x - bw / 2}" y="${h - padB - (c.v / vmax) * volH}" width="${bw}" height="${(c.v / vmax) * volH}" fill="${col}" opacity="0.22"/>`;
    });
    overlays.forEach((o) => { const d = path(o.values); if (d) out += `<path d="${d}" fill="none" stroke="${o.color}" stroke-width="${o.width || 1.4}" ${o.dash ? `stroke-dasharray="${o.dash}"` : ""} stroke-linejoin="round"><title>${o.label || ""}</title></path>`; });
    dots.forEach((d) => d.values.forEach((v, i) => { if (v != null) out += `<circle cx="${xAt(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="1.6" fill="${d.color}"/>`; }));
    if (ema) {
      let e = cs[0].c; const k = 2 / 21;
      const pts = cs.map((c, i) => { e = c.c * k + e * (1 - k); return `${xAt(i).toFixed(1)},${y(e).toFixed(1)}`; });
      out += `<polyline class="draw" style="--len:2400" points="${pts.join(" ")}" fill="none" stroke="var(--accent)" stroke-width="1.6" stroke-linejoin="round"/>`;
      const last = pts[pts.length - 1].split(",");
      out += `<circle class="ema-dot" cx="${last[0]}" cy="${last[1]}" r="3" fill="var(--accent)"/>`;
    }
    markers.forEach((m) => {
      const c = cs[m.index]; if (!c) return;
      const x = xAt(m.index), bull = m.bias === "bullish", bear = m.bias === "bearish";
      const yy = bull ? y(c.l) + 10 : y(c.h) - 10, col = bull ? "var(--up)" : bear ? "var(--down)" : "var(--tx-2)";
      const shape = bull ? `M${x - 4},${yy + 4}L${x + 4},${yy + 4}L${x},${yy - 3}Z` : bear ? `M${x - 4},${yy - 4}L${x + 4},${yy - 4}L${x},${yy + 3}Z` : `M${x},${yy - 4}L${x + 4},${yy}L${x},${yy + 4}L${x - 4},${yy}Z`;
      out += `<path d="${shape}" fill="${col}" opacity="0.9"><title>${TA.esc(m.label)}</title></path>`;
    });
    return `<svg class="${cls}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Candlestick chart${ema ? " with 20-period EMA" : ""}${overlays.length ? ", " + overlays.map((o) => o.label).join(", ") : ""}">${out}</svg>`;
  };
})();
