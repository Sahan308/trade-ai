/* TRADE-AI core: icons, formatting, motion helpers. Exposed on window.TA */
(function () {
  const TA = (window.TA = window.TA || {});

  // ---- Icon set (single consistent 24px stroke style) ----
  const P = {
    logo: '<path d="M4 17l5-5 4 3 7-8"/><path d="M15 7h5v5"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    x: '<path d="M7 7l10 10M17 7L7 17"/>',
    arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"/>',
    arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"/>',
    arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    minus: '<path d="M5 12h14"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/>',
    chart: '<path d="M4 4v16h16"/><path d="M8 15l3-4 3 2 4-6"/>',
    candles: '<path d="M7 3v4M7 15v6M17 3v6M17 17v4"/><rect x="5" y="7" width="4" height="8" rx="1"/><rect x="15" y="9" width="4" height="8" rx="1"/>',
    radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12l6-6"/>',
    history: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v4h4"/><path d="M12 8v4l3 2"/>',
    sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"/>',
    star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9 6.7 19.6l1-5.8L3.5 9.7l5.9-.9z"/>',
    zap: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    gauge: '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/>',
    bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4.5-6 8-6s7 2 8 6"/>',
    card: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>',
    plug: '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    wifiOff: '<path d="M3 3l18 18"/><path d="M8.5 16.5a5 5 0 0 1 7 0M5 12.5a10 10 0 0 1 5-2.7M14 9.8a10 10 0 0 1 5 2.7M12 20h.01"/>',
    database: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3 3 7 3s7-1.3 7-3v-6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    flask: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3"/><path d="M7.5 15h9"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9"/><path d="M4 4v5h5"/><path d="M4 13a8 8 0 0 0 14 4.5l2-2.5"/><path d="M20 20v-5h-5"/>',
    logout: '<path d="M15 4h4v16h-4"/><path d="M10 8l-4 4 4 4M6 12h10"/>'
  };
  TA.icon = (name, cls = "") =>
    `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${P[name] || ""}</svg>`;
  TA.hydrateIcons = (root = document) =>
    root.querySelectorAll("[data-icon]").forEach((el) => {
      el.insertAdjacentHTML("afterbegin", TA.icon(el.dataset.icon, el.dataset.iconClass || ""));
      el.removeAttribute("data-icon");
    });

  // ---- Formatting ----
  TA.fmtPrice = (n) => {
    if (n == null || isNaN(n)) return "—";
    const d = n >= 1000 ? 2 : n >= 1 ? 3 : 5;
    return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  TA.fmtUsd = (n) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  TA.fmtPct = (n) => (n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`);
  TA.fmtCompact = (n) =>
    n == null ? "—" : Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(n);
  TA.fmtTime = (d) =>
    new Date(d).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  TA.ago = (d) => {
    const s = Math.max(0, Math.round((Date.now() - new Date(d)) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    return `${Math.round(s / 3600)}h ago`;
  };
  TA.esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Direction text + icon so meaning never depends on colour alone
  TA.dirBadge = (dir) => {
    if (dir === "LONG") return `<span class="badge badge-long">${TA.icon("arrowUp", "icon-sm")}Long</span>`;
    if (dir === "SHORT") return `<span class="badge badge-short">${TA.icon("arrowDown", "icon-sm")}Short</span>`;
    return `<span class="badge badge-none">${TA.icon("minus", "icon-sm")}No trade</span>`;
  };
  TA.chg = (v) =>
    `<span class="chg ${v >= 0 ? "up" : "down"}">${TA.icon(v >= 0 ? "arrowUp" : "arrowDown", "icon-sm")}<span class="num">${TA.fmtPct(v)}</span><span class="sr-only">${v >= 0 ? "up" : "down"}</span></span>`;

  // ---- Motion ----
  TA.reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  TA.initReveal = (root = document) => {
    // Stagger grouped cards: children of [data-stagger] get increasing delays (capped).
    root.querySelectorAll("[data-stagger]").forEach((g) =>
      [...g.querySelectorAll(":scope > .reveal, :scope > * > .reveal")].forEach((el, i) => el.style.setProperty("--d", `${Math.min(i, 5) * 70}ms`)));
    const els = root.querySelectorAll(".reveal:not(.is-visible)");
    if (TA.reducedMotion() || !("IntersectionObserver" in window)) {
      els.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    let io;
    try {
      io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) { e.target.classList.add("is-visible"); io.unobserve(e.target); }
        }),
        { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
      );
      els.forEach((el) => io.observe(el));
      // Hide-until-visible only once observation is running, so a failure never leaves content invisible.
      document.documentElement.classList.add("js-motion");
    } catch (e) {
      els.forEach((el) => el.classList.add("is-visible"));
    }
  };

  // ---- Accessible modal with focus trap ----
  TA.modal = (() => {
    let el, lastFocus;
    function ensure() {
      if (el) return el;
      el = document.createElement("div");
      el.className = "modal";
      el.setAttribute("aria-hidden", "true");
      el.innerHTML = `<div class="modal-backdrop" data-close></div>
        <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modal-title">
          <button class="icon-btn modal-close" data-close aria-label="Close dialog">${TA.icon("close")}</button>
          <div class="modal-body"></div></div>`;
      document.body.appendChild(el);
      el.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) close(); });
      el.addEventListener("keydown", (e) => {
        if (e.key === "Escape") close();
        if (e.key === "Tab") {
          const f = [...el.querySelectorAll('button, [href], input, select, [tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled);
          if (!f.length) return;
          const first = f[0], last = f[f.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      });
      return el;
    }
    function open(html) {
      ensure();
      lastFocus = document.activeElement;
      el.querySelector(".modal-body").innerHTML = html;
      el.classList.add("open");
      el.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
      setTimeout(() => el.querySelector(".modal-close").focus(), 30);
    }
    function close() {
      if (!el) return;
      el.classList.remove("open");
      el.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
      if (lastFocus) lastFocus.focus();
    }
    return { open, close };
  })();

  TA.toast = (msg, icon = "info") => {
    let t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.innerHTML = `${TA.icon(icon)}<span>${TA.esc(msg)}</span>`;
    t.classList.add("show");
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove("show"), 3200);
  };
})();
