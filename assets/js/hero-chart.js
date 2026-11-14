/*
 * Hero chart animation (landing page only).
 * Draws the DEMO fixture once with an entrance animation (CSS, triggered by the parent .reveal),
 * then runs a slow simulated tick: the last candle drifts, and a new candle is added now and then.
 * Purely illustrative — the fixture is sample data and the motion is simulated, as the UI labels say.
 * Motion pauses offscreen / in a hidden tab, and is off entirely with prefers-reduced-motion.
 */
(function () {
  const TA = window.TA;
  const OPTS = { w: 600, h: 260, volume: true };
  const TICK_MS = 650, TWEEN_MS = 420, NEW_CANDLE_EVERY = 4, INTRO_MS = 1300;

  TA.heroChart = (box) => {
    if (!box) return;
    let cs = TA.DEMO.candles(56, 100, 7);
    const lo0 = Math.min(...cs.map((c) => c.l)), hi0 = Math.max(...cs.map((c) => c.h));
    const pad = (hi0 - lo0) * 0.12;
    const range = [lo0 - pad, hi0 + (hi0 - lo0) * 0.32];   // fixed scale + headroom for the badge
    const badge = `<span class="live-badge" aria-label="Live demo: simulated motion on sample data"><span class="live-dot" aria-hidden="true"></span>Live demo</span>`;
    const draw = () => (box.innerHTML = TA.candleChart(cs, { ...OPTS, range }) + badge);
    draw();

    if (TA.reducedMotion()) { box.classList.add("settled"); return; }

    // seeded walk so the simulation is calm and repeatable
    let seed = 42; const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    const step = (hi0 - lo0) * 0.016;
    let onScreen = false, timer = null, ticks = 0, raf = 0;

    function clampToRange(v) { return Math.min(range[1] - pad * 0.3, Math.max(range[0] + pad * 0.3, v)); }

    function tick() {
      ticks++;
      if (ticks % NEW_CANDLE_EVERY === 0) {
        const prev = cs[cs.length - 1];
        cs = cs.slice(1).concat({ t: prev.t + 3600e3, o: prev.c, h: prev.c, l: prev.c, c: prev.c, v: 200 + rnd() * 700 });
        box.classList.add("fresh");
        setTimeout(() => box.classList.remove("fresh"), 650);
      }
      const last = cs[cs.length - 1];
      // gentle mean reversion toward the recent average keeps it from wandering off-scale
      const mean = cs.slice(-12).reduce((a, c) => a + c.c, 0) / 12;
      const target = clampToRange(last.c + (rnd() - 0.5) * step * 2 + (mean - last.c) * 0.08);
      const from = last.c, t0 = performance.now();
      cancelAnimationFrame(raf);
      const anim = (now) => {
        const k = Math.min(1, (now - t0) / TWEEN_MS), e = 1 - Math.pow(1 - k, 3);
        last.c = from + (target - from) * e;
        last.h = Math.max(last.h, last.c); last.l = Math.min(last.l, last.c);
        last.v += 2;
        draw();
        if (k < 1) raf = requestAnimationFrame(anim);
      };
      raf = requestAnimationFrame(anim);
    }

    const running = () => onScreen && !document.hidden;
    function sync() {
      box.classList.toggle("paused", !running());
      if (running() && !timer && box.classList.contains("settled")) timer = setInterval(tick, TICK_MS);
      if (!running() && timer) { clearInterval(timer); timer = null; cancelAnimationFrame(raf); }
    }

    // Wait for the entrance (driven by the parent .reveal becoming visible), then go live.
    const host = box.closest(".reveal") || box;
    const startAfterIntro = () => setTimeout(() => { box.classList.add("settled"); sync(); }, INTRO_MS);
    if (host.classList.contains("is-visible")) startAfterIntro();
    else new MutationObserver((m, mo) => { if (host.classList.contains("is-visible")) { mo.disconnect(); startAfterIntro(); } })
      .observe(host, { attributes: true, attributeFilter: ["class"] });

    new IntersectionObserver((es) => { onScreen = es[0].isIntersecting; sync(); }).observe(box);
    document.addEventListener("visibilitychange", sync);
  };
})();
