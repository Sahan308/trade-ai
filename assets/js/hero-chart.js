/*
 * Hero chart (landing page only). Draws the DEMO fixture once; the entrance animation
 * (candles, volume, EMA line) is pure CSS, triggered when the parent .reveal scrolls into view.
 * There is deliberately NO ongoing motion: animating sample data could be mistaken for live
 * market activity. Ongoing chart updates belong only to real, validated market data (Milestone 2).
 */
(function () {
  const TA = window.TA;
  TA.heroChart = (box) => {
    if (!box) return;
    const cs = TA.DEMO.candles(56, 100, 7);
    box.innerHTML = TA.candleChart(cs, { w: 600, h: 260, volume: true });
    if (TA.reducedMotion()) box.classList.add("settled");
  };
})();
