(function () {
  const TA = window.TA, C = window.TRADE_AI_CONFIG;
  TA.hydrateIcons();

  // Config-driven pricing text
  const P = C.pricing;
  document.querySelectorAll('[data-cfg="trialSignals"]').forEach((e) => (e.textContent = P.trialSignals));
  document.querySelectorAll('[data-cfg="price"]').forEach((e) => (e.textContent = P.monthlyPrice));
  document.querySelectorAll('[data-cfg="trialDuration"]').forEach((e) => (e.textContent = P.trialDurationDays ? `${P.trialDurationDays} days` : "to be confirmed"));
  document.querySelectorAll('[data-cfg="renewal"]').forEach((e) => (e.textContent = P.renewalTerms || "to be confirmed"));
  document.querySelectorAll("[data-link]").forEach((a) => (a.href = C.links[a.dataset.link] || "#"));
  document.getElementById("yr").textContent = new Date().getFullYear();

  document.getElementById("subscribeBtn").addEventListener("click", () => {
    if (!P.checkoutEnabled) TA.toast("Checkout isn't live yet — start with the free trial for now.", "info");
  });

  // Hero chart (demo fixture, clearly labelled in markup)
  const hero = document.getElementById("heroChart");
  hero.innerHTML = TA.candleChart(TA.DEMO.candles(56, 100, 7), { w: 600, h: 260, volume: true });

  // Sample signals
  document.getElementById("samples").innerHTML = TA.DEMO.signals
    .map((s, i) => `<div class="reveal" style="--d:${i * 80}ms">${TA.signalCard(s)}</div>`).join("");

  // Nav: scrolled state + mobile menu
  const nav = document.getElementById("nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
  window.addEventListener("scroll", onScroll, { passive: true }); onScroll();
  const tgl = document.getElementById("navToggle"), menu = document.getElementById("mobileMenu");
  const setMenu = (open) => {
    menu.classList.toggle("open", open); tgl.setAttribute("aria-expanded", open);
    tgl.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    tgl.innerHTML = TA.icon(open ? "close" : "menu");
  };
  tgl.addEventListener("click", () => setMenu(!menu.classList.contains("open")));
  menu.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && menu.classList.contains("open")) { setMenu(false); tgl.focus(); } });

  // FAQ accordion
  document.querySelectorAll(".faq-q").forEach((b, i) => {
    const panel = b.nextElementSibling; const id = `faq-a-${i}`;
    panel.id = id; b.setAttribute("aria-controls", id); b.id = `faq-q-${i}`; panel.setAttribute("aria-labelledby", b.id);
    b.addEventListener("click", () => b.setAttribute("aria-expanded", b.getAttribute("aria-expanded") !== "true"));
  });

  TA.initReveal();
})();
