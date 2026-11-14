/*
 * Technical analysis — JavaScript twin of backend/app/analysis/{indicators,patterns}.py.
 * Formulas, warm-up rules and thresholds are documented in the Python files and must stay identical;
 * backend/tests/test_parity.py runs both on the same candles and fails if any output differs.
 * Outputs: arrays aligned with the input; warm-up positions are null.
 */
(function () {
  const root = typeof window !== "undefined" ? window : globalThis;
  const TA = (root.TA = root.TA || {});
  const nulls = (n) => new Array(n).fill(null);
  const sum = (a) => a.reduce((s, v) => s + v, 0);
  const maxOf = (a) => a.reduce((m, v) => (v > m ? v : m), -Infinity);
  const minOf = (a) => a.reduce((m, v) => (v < m ? v : m), Infinity);

  // ---------------- Moving averages ----------------
  function sma(x, n) {
    const out = nulls(x.length); let s = 0;
    for (let i = 0; i < x.length; i++) { s += x[i]; if (i >= n) s -= x[i - n]; if (i >= n - 1) out[i] = s / n; }
    return out;
  }
  function ema(x, n) {
    const out = nulls(x.length), a = 2 / (n + 1);
    const start = x.findIndex((v) => v !== null && v !== undefined);
    if (start < 0 || x.length - start < n) return out;
    let prev = sum(x.slice(start, start + n)) / n; out[start + n - 1] = prev;
    for (let i = start + n; i < x.length; i++) { prev = a * x[i] + (1 - a) * prev; out[i] = prev; }
    return out;
  }
  function wma(x, n) {
    const out = nulls(x.length), d = (n * (n + 1)) / 2;
    for (let i = n - 1; i < x.length; i++) { let s = 0; for (let k = 0; k < n; k++) s += x[i - n + 1 + k] * (k + 1); out[i] = s / d; }
    return out;
  }
  function vwma(close, vol, n) {
    const out = nulls(close.length);
    for (let i = n - 1; i < close.length; i++) {
      let v = 0, cv = 0; for (let j = i - n + 1; j <= i; j++) { v += vol[j]; cv += close[j] * vol[j]; }
      out[i] = v ? cv / v : null;
    }
    return out;
  }
  function wilder(x, n, first = 0) {
    const out = nulls(x.length);
    if (x.length - first < n) return out;
    let prev = sum(x.slice(first, first + n)) / n; out[first + n - 1] = prev;
    for (let i = first + n; i < x.length; i++) { prev = (prev * (n - 1) + x[i]) / n; out[i] = prev; }
    return out;
  }
  function smaSkip(x, n) {
    const out = nulls(x.length);
    for (let i = n - 1; i < x.length; i++) { const w = x.slice(i - n + 1, i + 1); if (w.every((v) => v !== null)) out[i] = sum(w) / n; }
    return out;
  }

  // ---------------- Momentum ----------------
  function rsi(close, n = 14) {
    const out = nulls(close.length);
    if (close.length <= n) return out;
    const g = [0], l = [0];
    for (let i = 1; i < close.length; i++) { g.push(Math.max(close[i] - close[i - 1], 0)); l.push(Math.max(close[i - 1] - close[i], 0)); }
    const ag = wilder(g, n, 1), al = wilder(l, n, 1);
    for (let i = n; i < close.length; i++) out[i] = ag[i] === 0 && al[i] === 0 ? 50 : al[i] === 0 ? 100 : 100 - 100 / (1 + ag[i] / al[i]);
    return out;
  }
  function macd(close, fast = 12, slow = 26, signal = 9) {
    const f = ema(close, fast), s = ema(close, slow);
    const line = f.map((a, i) => (a !== null && s[i] !== null ? a - s[i] : null));
    const sig = ema(line, signal);
    return { macd: line, signal: sig, histogram: line.map((a, i) => (a !== null && sig[i] !== null ? a - sig[i] : null)) };
  }
  function stochastic(high, low, close, k = 14, smoothK = 3, d = 3) {
    const raw = nulls(close.length);
    for (let i = k - 1; i < close.length; i++) {
      const hh = maxOf(high.slice(i - k + 1, i + 1)), ll = minOf(low.slice(i - k + 1, i + 1));
      raw[i] = hh === ll ? 50 : (100 * (close[i] - ll)) / (hh - ll);
    }
    const kk = smaSkip(raw, smoothK);
    return { k: kk, d: smaSkip(kk, d) };
  }
  function cci(high, low, close, n = 20) {
    const tp = close.map((c, i) => (high[i] + low[i] + c) / 3), m = sma(tp, n), out = nulls(tp.length);
    for (let i = n - 1; i < tp.length; i++) {
      let md = 0; for (let j = i - n + 1; j <= i; j++) md += Math.abs(tp[j] - m[i]); md /= n;
      out[i] = md === 0 ? 0 : (tp[i] - m[i]) / (0.015 * md);
    }
    return out;
  }
  function mfi(high, low, close, vol, n = 14) {
    const tp = close.map((c, i) => (high[i] + low[i] + c) / 3), out = nulls(tp.length);
    for (let i = n; i < tp.length; i++) {
      let pos = 0, neg = 0;
      for (let j = i - n + 1; j <= i; j++) { const f = tp[j] * vol[j]; if (tp[j] > tp[j - 1]) pos += f; else if (tp[j] < tp[j - 1]) neg += f; }
      out[i] = pos === 0 && neg === 0 ? 50 : neg === 0 ? 100 : 100 - 100 / (1 + pos / neg);
    }
    return out;
  }

  // ---------------- Volatility ----------------
  function trueRange(high, low, close) {
    const out = [high[0] - low[0]];
    for (let i = 1; i < close.length; i++) out.push(Math.max(high[i] - low[i], Math.abs(high[i] - close[i - 1]), Math.abs(low[i] - close[i - 1])));
    return out;
  }
  const atr = (high, low, close, n = 14) => (close.length ? wilder(trueRange(high, low, close), n) : []);
  function bollinger(close, n = 20, k = 2) {
    const mid = sma(close, n), up = nulls(close.length), lo = nulls(close.length);
    for (let i = n - 1; i < close.length; i++) {
      let v = 0; for (let j = i - n + 1; j <= i; j++) v += (close[j] - mid[i]) ** 2;
      const sd = Math.sqrt(v / n); up[i] = mid[i] + k * sd; lo[i] = mid[i] - k * sd;
    }
    return { middle: mid, upper: up, lower: lo };
  }
  function keltner(high, low, close, n = 20, mult = 2, atrN = 10) {
    const mid = ema(close, n), a = atr(high, low, close, atrN);
    return { middle: mid, upper: mid.map((m, i) => (m !== null && a[i] !== null ? m + mult * a[i] : null)), lower: mid.map((m, i) => (m !== null && a[i] !== null ? m - mult * a[i] : null)) };
  }

  // ---------------- Trend ----------------
  function adx(high, low, close, n = 14) {
    const L = close.length, pdi = nulls(L), mdi = nulls(L), ax = nulls(L);
    if (L <= 2 * n) return { plus_di: pdi, minus_di: mdi, adx: ax };
    const tr = trueRange(high, low, close), pdm = new Array(L).fill(0), mdm = new Array(L).fill(0);
    for (let i = 1; i < L; i++) {
      const up = high[i] - high[i - 1], dn = low[i - 1] - low[i];
      pdm[i] = up > dn && up > 0 ? up : 0; mdm[i] = dn > up && dn > 0 ? dn : 0;
    }
    let sTr = sum(tr.slice(1, n + 1)), sP = sum(pdm.slice(1, n + 1)), sM = sum(mdm.slice(1, n + 1));
    const dx = nulls(L);
    for (let i = n; i < L; i++) {
      if (i > n) { sTr = sTr - sTr / n + tr[i]; sP = sP - sP / n + pdm[i]; sM = sM - sM / n + mdm[i]; }
      const p = sTr ? (100 * sP) / sTr : 0, m = sTr ? (100 * sM) / sTr : 0;
      pdi[i] = p; mdi[i] = m; dx[i] = p + m === 0 ? 0 : (100 * Math.abs(p - m)) / (p + m);
    }
    let prev = sum(dx.slice(n, 2 * n)) / n; ax[2 * n - 1] = prev;
    for (let i = 2 * n; i < L; i++) { prev = (prev * (n - 1) + dx[i]) / n; ax[i] = prev; }
    return { plus_di: pdi, minus_di: mdi, adx: ax };
  }
  function supertrend(high, low, close, n = 10, mult = 3) {
    const L = close.length, a = atr(high, low, close, n), line = nulls(L), dir = nulls(L);
    let fu = null, fl = null, d = 1;
    for (let i = 0; i < L; i++) {
      if (a[i] === null) continue;
      const hl2 = (high[i] + low[i]) / 2, bu = hl2 + mult * a[i], bl = hl2 - mult * a[i];
      if (fu === null) { fu = bu; fl = bl; d = close[i] >= hl2 ? 1 : -1; }
      else {
        fu = bu < fu || close[i - 1] > fu ? bu : fu;
        fl = bl > fl || close[i - 1] < fl ? bl : fl;
        if (d === 1 && close[i] < fl) d = -1; else if (d === -1 && close[i] > fu) d = 1;
      }
      line[i] = d === 1 ? fl : fu; dir[i] = d;
    }
    return { supertrend: line, direction: dir };
  }
  function ichimoku(high, low, close, tenkan = 9, kijun = 26, senkouB = 52, shift = 26) {
    const L = close.length;
    const mid = (p, i) => (i >= p - 1 ? (maxOf(high.slice(i - p + 1, i + 1)) + minOf(low.slice(i - p + 1, i + 1))) / 2 : null);
    const t = [], k = [], rb = [];
    for (let i = 0; i < L; i++) { t.push(mid(tenkan, i)); k.push(mid(kijun, i)); rb.push(mid(senkouB, i)); }
    const ra = t.map((a, i) => (a !== null && k[i] !== null ? (a + k[i]) / 2 : null));
    return {
      tenkan: t, kijun: k,
      span_a: ra.map((_, i) => (i >= shift ? ra[i - shift] : null)),
      span_b: rb.map((_, i) => (i >= shift ? rb[i - shift] : null)),
      chikou: close.map((_, i) => (i + shift < L ? close[i + shift] : null))
    };
  }
  function parabolicSar(high, low, step = 0.02, maxStep = 0.2) {
    const L = high.length, out = nulls(L);
    if (L < 2) return out;
    let up = high[1] >= high[0], sar = up ? low[0] : high[0], ep = up ? high[1] : low[1], af = step;
    for (let i = 1; i < L; i++) {
      sar = sar + af * (ep - sar);
      if (up) {
        sar = Math.min(sar, low[i - 1], i >= 2 ? low[i - 2] : low[i - 1]);
        if (low[i] < sar) { up = false; sar = ep; ep = low[i]; af = step; }
        else if (high[i] > ep) { ep = high[i]; af = Math.min(af + step, maxStep); }
      } else {
        sar = Math.max(sar, high[i - 1], i >= 2 ? high[i - 2] : high[i - 1]);
        if (high[i] > sar) { up = true; sar = ep; ep = high[i]; af = step; }
        else if (low[i] < ep) { ep = low[i]; af = Math.min(af + step, maxStep); }
      }
      out[i] = sar;
    }
    return out;
  }

  // ---------------- Volume ----------------
  function obv(close, vol) {
    const out = new Array(close.length).fill(0); let s = 0;
    for (let i = 1; i < close.length; i++) { s += close[i] > close[i - 1] ? vol[i] : close[i] < close[i - 1] ? -vol[i] : 0; out[i] = s; }
    return out;
  }
  function vwap(t, high, low, close, vol) {
    const out = nulls(close.length); let pv = 0, vv = 0, day = null;
    for (let i = 0; i < t.length; i++) {
      const d = Math.floor(t[i] / 86400000);
      if (d !== day) { day = d; pv = 0; vv = 0; }
      pv += ((high[i] + low[i] + close[i]) / 3) * vol[i]; vv += vol[i];
      out[i] = vv ? pv / vv : null;
    }
    return out;
  }
  function volumeProfile(high, low, close, vol, bins = 24, valueArea = 0.7) {
    if (!close.length) return { bins: [], poc: null, value_area_high: null, value_area_low: null };
    const lo = minOf(low), hi = maxOf(high), width = hi > lo ? (hi - lo) / bins : 1, vols = new Array(bins).fill(0);
    for (let i = 0; i < close.length; i++) {
      const idx = hi > lo ? Math.min(bins - 1, Math.trunc(((high[i] + low[i] + close[i]) / 3 - lo) / width)) : 0;
      vols[idx] += vol[i];
    }
    let poc = 0; for (let b = 1; b < bins; b++) if (vols[b] > vols[poc]) poc = b;
    const total = sum(vols); let inside = vols[poc], a = poc, b = poc;
    while (total && inside / total < valueArea && (a > 0 || b < bins - 1)) {
      const below = a > 0 ? vols[a - 1] : -1, above = b < bins - 1 ? vols[b + 1] : -1;
      if (above >= below) { b++; inside += vols[b]; } else { a--; inside += vols[a]; }
    }
    const edges = vols.map((_, i) => [lo + i * width, lo + (i + 1) * width]);
    return { bins: edges.map((e, i) => ({ low: e[0], high: e[1], volume: vols[i] })), poc: (edges[poc][0] + edges[poc][1]) / 2, value_area_low: edges[a][0], value_area_high: edges[b][1] };
  }

  // ---------------- Levels ----------------
  const FIB_RATIOS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
  function fibonacci(high, low, lookback = 100) {
    if (!high.length) return null;
    const s = Math.max(0, high.length - lookback);
    let hiI = s, loI = s;
    for (let i = s + 1; i < high.length; i++) { if (high[i] > high[hiI]) hiI = i; if (low[i] < low[loI]) loI = i; }
    const hi = high[hiI], lo = low[loI], up = hiI > loI, levels = {};
    FIB_RATIOS.forEach((r) => { levels[String(r)] = up ? hi - r * (hi - lo) : lo + r * (hi - lo); });
    return { direction: up ? "up" : "down", swing_high: hi, swing_low: lo, swing_high_index: hiI, swing_low_index: loI, levels };
  }
  function pivots(t, high, low, close, intervalMs) {
    if (close.length < 2) return null;
    let h, l, c, basis;
    if (intervalMs >= 86400000) { h = high[high.length - 2]; l = low[low.length - 2]; c = close[close.length - 2]; basis = "previous bar"; }
    else {
      const today = Math.floor(t[t.length - 1] / 86400000), idx = [];
      t.forEach((x, i) => { if (Math.floor(x / 86400000) === today - 1) idx.push(i); });
      if (!idx.length) return null;
      h = maxOf(idx.map((i) => high[i])); l = minOf(idx.map((i) => low[i])); c = close[idx[idx.length - 1]]; basis = "previous UTC day";
    }
    const p = (h + l + c) / 3;
    return { basis, p, r1: 2 * p - l, s1: 2 * p - h, r2: p + (h - l), s2: p - (h - l), r3: h + 2 * (p - l), s3: l - 2 * (h - p) };
  }

  // ---------------- Candlestick patterns (see patterns.py for definitions) ----------------
  const K = { DOJI_BODY: 0.1, SMALL_BODY: 0.3, LONG_BODY: 1.3, SHADOW_MULT: 2.0, TINY_SHADOW: 0.1, MARUBOZU_SHADOW: 0.05, TWEEZER_TOL: 0.001, HISTORY: 10 };
  function candle(o, h, l, c) {
    const top = Math.max(o, c), bot = Math.min(o, c);
    return { o, h, l, c, body: Math.abs(c - o), range: h - l, upper: h - top, lower: bot - l, bull: c > o, bear: c < o, mid: (o + c) / 2, top, bot };
  }
  const hit = (pattern, bias, idx) => ({ pattern, bias, index: idx[idx.length - 1], candles: idx });

  function detectCandlestickPatterns(o, h, l, c) {
    const cs = o.map((_, i) => candle(o[i], h[i], l[i], c[i])), out = [];
    for (let i = K.HISTORY; i < cs.length; i++) {
      const k = cs[i], p = cs[i - 1], q = cs[i - 2], r = k.range;
      if (r <= 0) continue;
      let avg = 0; for (let j = i - K.HISTORY; j < i; j++) avg += cs[j].body; avg /= K.HISTORY;
      const down = cs[i - 1].c < cs[i - 6].c, up = cs[i - 1].c > cs[i - 6].c;
      if (k.body <= K.DOJI_BODY * r) {
        if (k.upper <= K.TINY_SHADOW * r && k.lower >= 0.6 * r) out.push(hit("Dragonfly doji", down ? "bullish" : "neutral", [i]));
        else if (k.lower <= K.TINY_SHADOW * r && k.upper >= 0.6 * r) out.push(hit("Gravestone doji", up ? "bearish" : "neutral", [i]));
        else if (k.upper >= 0.3 * r && k.lower >= 0.3 * r && r >= 1.5 * avg) out.push(hit("Long-legged doji", "neutral", [i]));
        else out.push(hit("Doji", "neutral", [i]));
      } else {
        const hammer = k.lower >= K.SHADOW_MULT * k.body && k.upper <= K.TINY_SHADOW * r * 1.5 && k.body <= K.SMALL_BODY * r;
        const inv = k.upper >= K.SHADOW_MULT * k.body && k.lower <= K.TINY_SHADOW * r * 1.5 && k.body <= K.SMALL_BODY * r;
        if (hammer && down) out.push(hit("Hammer", "bullish", [i]));
        else if (hammer && up) out.push(hit("Hanging man", "bearish", [i]));
        if (inv && down) out.push(hit("Inverted hammer", "bullish", [i]));
        else if (inv && up) out.push(hit("Shooting star", "bearish", [i]));
        if (k.upper <= K.MARUBOZU_SHADOW * r && k.lower <= K.MARUBOZU_SHADOW * r && k.body >= K.LONG_BODY * avg)
          out.push(hit(k.bull ? "Bullish marubozu" : "Bearish marubozu", k.bull ? "bullish" : "bearish", [i]));
        if (k.body <= K.SMALL_BODY * r && k.upper >= k.body && k.lower >= k.body && !hammer && !inv) out.push(hit("Spinning top", "neutral", [i]));
      }
      if (p.bear && k.bull && k.o <= p.c && k.c >= p.o && k.body > p.body && down) out.push(hit("Bullish engulfing", "bullish", [i - 1, i]));
      if (p.bull && k.bear && k.o >= p.c && k.c <= p.o && k.body > p.body && up) out.push(hit("Bearish engulfing", "bearish", [i - 1, i]));
      if (p.bear && p.body >= avg && k.bull && k.top < p.o && k.bot > p.c && down) out.push(hit("Bullish harami", "bullish", [i - 1, i]));
      if (p.bull && p.body >= avg && k.bear && k.top < p.c && k.bot > p.o && up) out.push(hit("Bearish harami", "bearish", [i - 1, i]));
      if (p.bear && p.body >= avg && k.bull && k.o < p.c && p.mid < k.c && k.c < p.o && down) out.push(hit("Piercing line", "bullish", [i - 1, i]));
      if (p.bull && p.body >= avg && k.bear && k.o > p.c && p.o < k.c && k.c < p.mid && up) out.push(hit("Dark cloud cover", "bearish", [i - 1, i]));
      if (up && p.bull && k.bear && Math.abs(k.h - p.h) <= K.TWEEZER_TOL * p.h) out.push(hit("Tweezer top", "bearish", [i - 1, i]));
      if (down && p.bear && k.bull && Math.abs(k.l - p.l) <= K.TWEEZER_TOL * p.l) out.push(hit("Tweezer bottom", "bullish", [i - 1, i]));
      const pSmall = p.body <= K.SMALL_BODY * Math.max(p.range, 1e-12);
      if (q.bear && q.body >= K.LONG_BODY * avg && pSmall && p.top < q.c && k.bull && k.c > q.mid && cs[i - 2].c < cs[i - 7].c) out.push(hit("Morning star", "bullish", [i - 2, i - 1, i]));
      if (q.bull && q.body >= K.LONG_BODY * avg && pSmall && p.bot > q.c && k.bear && k.c < q.mid && cs[i - 2].c > cs[i - 7].c) out.push(hit("Evening star", "bearish", [i - 2, i - 1, i]));
      const three = [q, p, k];
      if (three.every((x) => x.bull && x.body >= 0.6 * avg && x.upper <= 0.3 * x.range) && q.c < p.c && p.c < k.c && q.o < p.o && p.o <= q.c && p.o < k.o && k.o <= p.c) out.push(hit("Three white soldiers", "bullish", [i - 2, i - 1, i]));
      if (three.every((x) => x.bear && x.body >= 0.6 * avg && x.lower <= 0.3 * x.range) && q.c > p.c && p.c > k.c && q.c <= p.o && p.o < q.o && p.c <= k.o && k.o < p.o) out.push(hit("Three black crows", "bearish", [i - 2, i - 1, i]));
      if (q.bear && q.body >= avg && p.bull && p.top < q.o && p.bot > q.c && k.bull && k.c > q.o) out.push(hit("Three inside up", "bullish", [i - 2, i - 1, i]));
      if (q.bull && q.body >= avg && p.bear && p.top < q.c && p.bot > q.o && k.bear && k.c < q.o) out.push(hit("Three inside down", "bearish", [i - 2, i - 1, i]));
      if (q.bear && p.bull && p.o <= q.c && p.c >= q.o && p.body > q.body && k.bull && k.c > p.c) out.push(hit("Three outside up", "bullish", [i - 2, i - 1, i]));
      if (q.bull && p.bear && p.o >= q.c && p.c <= q.o && p.body > q.body && k.bear && k.c < p.c) out.push(hit("Three outside down", "bearish", [i - 2, i - 1, i]));
    }
    return out;
  }

  // ---------------- Formations ----------------
  function swingPoints(high, low, k = 3) {
    const hs = [], ls = [];
    for (let i = k; i < high.length - k; i++) {
      let isH = true, isL = true;
      for (let j = i - k; j <= i + k; j++) { if (j === i) continue; if (!(high[i] > high[j])) isH = false; if (!(low[i] < low[j])) isL = false; }
      if (isH) hs.push(i); if (isL) ls.push(i);
    }
    return { highs: hs, lows: ls };
  }
  function doubleTopsBottoms(high, low, close, k = 3, tolerance = 0.005, minGap = 5) {
    const sw = swingPoints(high, low, k), out = [];
    for (const [kind, peaks, troughs, price, opp] of [["Double top", sw.highs, sw.lows, high, low], ["Double bottom", sw.lows, sw.highs, low, high]]) {
      for (let x = 0; x + 1 < peaks.length; x++) {
        const a = peaks[x], b = peaks[x + 1];
        if (b - a < minGap || Math.abs(price[a] - price[b]) > tolerance * price[a]) continue;
        const between = troughs.filter((t) => a < t && t < b);
        if (!between.length) continue;
        let neckI = between[0];
        for (const t of between) if (kind === "Double top" ? opp[t] < opp[neckI] : opp[t] > opp[neckI]) neckI = t;
        const neck = opp[neckI];
        let conf = null;
        for (let j = b + 1; j < close.length; j++) if (kind === "Double top" ? close[j] < neck : close[j] > neck) { conf = j; break; }
        out.push({ formation: kind, bias: kind === "Double top" ? "bearish" : "bullish", points: [a, neckI, b], neckline: neck, status: conf !== null ? "confirmed" : "forming", confirmed_index: conf });
      }
    }
    return out;
  }

  TA.Analysis = {
    sma, ema, wma, vwma, rsi, macd, stochastic, cci, mfi, trueRange, atr, bollinger, keltner, adx, supertrend, ichimoku,
    parabolicSar, obv, vwap, volumeProfile, fibonacci, pivots, detectCandlestickPatterns, swingPoints, doubleTopsBottoms, FIB_RATIOS
  };
})();
