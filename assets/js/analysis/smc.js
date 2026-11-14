/*
 * Smart Money Concepts — JavaScript twin of backend/app/analysis/smc.py (definitions documented there).
 * Algorithmic interpretations of price action; they do not prove institutional activity.
 * Parity with Python is checked by backend/tests/test_parity.py.
 */
(function () {
  const root = typeof window !== "undefined" ? window : globalThis;
  const TA = (root.TA = root.TA || {});
  const A = () => TA.Analysis;

  function structure(o, h, l, c, k = 3) {
    const sw = A().swingPoints(h, l, k), highs = sw.highs.slice().sort((a, b) => a - b), lows = sw.lows.slice().sort((a, b) => a - b);
    const events = []; let trend = null, sh = null, sl = null, hp = 0, lp = 0;
    for (let j = 0; j < c.length; j++) {
      while (hp < highs.length && highs[hp] + k <= j) { sh = [highs[hp], h[highs[hp]], false]; hp++; }
      while (lp < lows.length && lows[lp] + k <= j) { sl = [lows[lp], l[lows[lp]], false]; lp++; }
      if (sh && !sh[2] && c[j] > sh[1]) {
        events.push({ type: trend === "bearish" ? "CHOCH" : "BOS", direction: "bullish", level: sh[1], swing_index: sh[0], index: j }); sh[2] = true; trend = "bullish";
      } else if (sl && !sl[2] && c[j] < sl[1]) {
        events.push({ type: trend === "bullish" ? "CHOCH" : "BOS", direction: "bearish", level: sl[1], swing_index: sl[0], index: j }); sl[2] = true; trend = "bearish";
      }
    }
    return events;
  }

  function orderBlocks(o, h, l, c, events) {
    const out = [];
    for (const e of events) {
      const b = e.index, s = e.swing_index, bull = e.direction === "bullish";
      let i = -1; for (let x = s; x < b; x++) if (bull ? c[x] < o[x] : c[x] > o[x]) i = x;
      if (i < 0) continue;
      const lo = l[i], hi = h[i]; let status = "fresh", mit = null, brk = null;
      for (let j = b + 1; j < c.length; j++) {
        if (bull) { if (c[j] < lo) { status = "broken"; brk = j; break; } if (mit === null && l[j] <= hi) { status = "mitigated"; mit = j; } }
        else { if (c[j] > hi) { status = "broken"; brk = j; break; } if (mit === null && h[j] >= lo) { status = "mitigated"; mit = j; } }
      }
      out.push({ direction: e.direction, index: i, low: lo, high: hi, created_index: b, status, mitigated_index: mit, broken_index: brk, from_event: e.type });
    }
    return out;
  }

  function fairValueGaps(h, l, c, minFvgAtr = 0.1) {
    const a = A().atr(h, l, c, 14), out = [];
    for (let i = 2; i < c.length; i++) {
      if (a[i] === null) continue;
      for (const bull of [true, false]) {
        const lo = bull ? h[i - 2] : h[i], hi = bull ? l[i] : l[i - 2];
        if (hi - lo <= 0 || hi - lo < minFvgAtr * a[i]) continue;
        let status = "open", touched = null, filled = null;
        for (let j = i + 1; j < c.length; j++) {
          if (bull) { if (l[j] <= lo) { status = "filled"; filled = j; break; } if (touched === null && l[j] <= hi) { status = "partial"; touched = j; } }
          else { if (h[j] >= hi) { status = "filled"; filled = j; break; } if (touched === null && h[j] >= lo) { status = "partial"; touched = j; } }
        }
        out.push({ direction: bull ? "bullish" : "bearish", index: i - 1, low: lo, high: hi, status, touched_index: touched, filled_index: filled });
      }
    }
    return out;
  }

  function liquidity(h, l, c, k = 3, eqTol = 0.001) {
    const sw = A().swingPoints(h, l, k), levels = [];
    for (const [side, idxs, price] of [["BSL", sw.highs, h], ["SSL", sw.lows, l]]) {
      for (const s of idxs) {
        const lvl = price[s]; let done = false;
        for (let j = s + k + 1; j < c.length; j++) {
          if (side === "BSL" && h[j] > lvl) { levels.push({ side, index: s, level: lvl, status: c[j] < lvl ? "swept" : "taken", event_index: j }); done = true; break; }
          if (side === "SSL" && l[j] < lvl) { levels.push({ side, index: s, level: lvl, status: c[j] > lvl ? "swept" : "taken", event_index: j }); done = true; break; }
        }
        if (!done) levels.push({ side, index: s, level: lvl, status: "resting", event_index: null });
      }
    }
    for (const x of levels) x.equal = levels.some((y) => y !== x && y.side === x.side && Math.abs(y.level - x.level) <= eqTol * x.level);
    levels.sort((a, b) => a.index - b.index || (a.side < b.side ? -1 : a.side > b.side ? 1 : 0));
    return { levels, sweeps: levels.filter((x) => x.status === "swept") };
  }

  function premiumDiscount(h, l, c, k = 3) {
    const sw = A().swingPoints(h, l, k);
    if (!sw.highs.length || !sw.lows.length) return null;
    const hiI = sw.highs[sw.highs.length - 1], loI = sw.lows[sw.lows.length - 1], hi = h[hiI], lo = l[loI];
    if (hi <= lo) return null;
    const eq = (hi + lo) / 2, px = c[c.length - 1];
    return { range_high: hi, range_low: lo, equilibrium: eq, zone: px > eq ? "premium" : px < eq ? "discount" : "equilibrium", position: (px - lo) / (hi - lo), high_index: hiI, low_index: loI };
  }

  function inducements(h, l, c, events, obs) {
    const minor = A().swingPoints(h, l, 1), out = [];
    for (const e of events) {
      const ob = obs.find((x) => x.created_index === e.index); if (!ob) continue;
      const bull = e.direction === "bullish", pts = bull ? minor.lows : minor.highs;
      const cand = pts.find((p) => p > e.index && (bull ? l[p] > ob.high : h[p] < ob.low));
      if (cand === undefined) continue;
      const lvl = bull ? l[cand] : h[cand];
      let taken = null; for (let j = cand + 2; j < c.length; j++) if (bull ? l[j] < lvl : h[j] > lvl) { taken = j; break; }
      out.push({ direction: e.direction, index: cand, level: lvl, taken_index: taken, status: taken !== null ? "taken" : "untaken", event_index: e.index });
    }
    return out;
  }

  function analyzeSmc(o, h, l, c, k = 3) {
    const ev = structure(o, h, l, c, k), obs = orderBlocks(o, h, l, c, ev);
    return { structure: ev, trend: ev.length ? ev[ev.length - 1].direction : null, order_blocks: obs, fvgs: fairValueGaps(h, l, c), liquidity: liquidity(h, l, c, k), premium_discount: premiumDiscount(h, l, c, k), inducements: inducements(h, l, c, ev, obs) };
  }

  TA.SMC = { structure, orderBlocks, fairValueGaps, liquidity, premiumDiscount, inducements, analyzeSmc };
})();
