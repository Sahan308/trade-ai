// Runs the browser TA library in Node for the parity test. Reads candles JSON on stdin, prints results JSON.
const fs = require("fs"), path = require("path");
globalThis.window = globalThis;
require(path.resolve(__dirname, "../../assets/js/analysis/ta.js"));
require(path.resolve(__dirname, "../../assets/js/analysis/smc.js"));
const A = globalThis.TA.Analysis;
const { t, o, h, l, c, v, interval_ms } = JSON.parse(fs.readFileSync(0, "utf8"));
const out = {
  sma: A.sma(c, 20), ema: A.ema(c, 20), wma: A.wma(c, 20), vwma: A.vwma(c, v, 20), rsi: A.rsi(c), macd: A.macd(c),
  stochastic: A.stochastic(h, l, c), cci: A.cci(h, l, c), mfi: A.mfi(h, l, c, v), atr: A.atr(h, l, c),
  bollinger: A.bollinger(c), keltner: A.keltner(h, l, c), adx: A.adx(h, l, c), supertrend: A.supertrend(h, l, c),
  ichimoku: A.ichimoku(h, l, c), psar: A.parabolicSar(h, l), obv: A.obv(c, v), vwap: A.vwap(t, h, l, c, v),
  volume_profile: A.volumeProfile(h, l, c, v), fibonacci: A.fibonacci(h, l), pivots: A.pivots(t, h, l, c, interval_ms),
  patterns: A.detectCandlestickPatterns(o, h, l, c), swings: A.swingPoints(h, l), formations: A.doubleTopsBottoms(h, l, c),
  smc: globalThis.TA.SMC.analyzeSmc(o, h, l, c)
};
process.stdout.write(JSON.stringify(out));
