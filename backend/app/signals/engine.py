"""Rule-based signal engine for strategy `smc_trend_pullback`.

Idea (LONG; SHORT is the mirror): the market is trending up on this timeframe, SMC structure agrees,
and price has pulled back to a recent bullish order block or fair value gap. Entry = that zone,
stop = just beyond it, targets = resting buy-side liquidity above (else R multiples).
Every hard requirement that fails produces NO TRADE with the reason. NO TRADE is a normal output.

The score is a HEURISTIC: supporting weights minus conflicting weights, clamped to 0–100.
It is not a probability of winning and has not been validated against outcomes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..analysis import indicators as ind
from ..analysis.patterns import detect_candlestick_patterns, double_tops_bottoms
from ..analysis.smc import analyze_smc
from ..providers.base import INTERVAL_MS
from .strategy import StrategyConfig

SCORE_NOTE = "Heuristic setup score (0–100): supporting minus conflicting evidence weights. Not a win probability."


def _closed(series: dict, interval: str, now: datetime) -> dict:
    """Keep only candles that have closed by `now` (the forming candle is excluded)."""
    step = INTERVAL_MS[interval]
    now_ms = now.timestamp() * 1000
    keep = [i for i, t in enumerate(series["t"]) if t + step <= now_ms]
    return {k: [series[k][i] for i in keep] for k in ("t", "o", "h", "l", "c", "v")}


def _bias(series: dict) -> str | None:
    c = series["c"]
    if len(c) < 60:
        return None
    e = ind.ema(c, 50)
    if e[-1] is None or e[-6] is None:
        return None
    if c[-1] > e[-1] and e[-1] > e[-6]:
        return "up"
    if c[-1] < e[-1] and e[-1] < e[-6]:
        return "down"
    return "neutral"


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def evaluate(series: dict, htf_series: dict | None, *, symbol: str, market: str, source: str,
             cfg: StrategyConfig, now: datetime, gaps: int = 0, funding_rate: float | None = None) -> dict:
    step = INTERVAL_MS[cfg.timeframe]
    base = {
        "symbol": symbol, "market": market, "timeframe": cfg.timeframe, "strategy": cfg.name,
        "strategy_version": cfg.version, "profile": cfg.profile, "config": cfg.snapshot(), "config_hash": cfg.hash(),
        "generated_at": now.isoformat(), "data_source": source, "score_note": SCORE_NOTE,
    }

    def no_trade(reasons, **extra):
        out = {**base, "side": "NO TRADE", "lifecycle": "no_trade", "reasons": reasons,
               "score": extra.pop("score", base.get("score")),
               "supporting": extra.pop("supporting", base.get("supporting", [])),
               "conflicting": extra.pop("conflicting", base.get("conflicting", [])), **extra}
        out["explanation"] = "No trade: " + "; ".join(reasons) + "."
        out["fingerprint"] = f"{symbol}|{market}|{cfg.timeframe}|NO_TRADE|{cfg.name}@{cfg.version}|{out.get('data_as_of')}"
        return out

    s = _closed(series, cfg.timeframe, now)
    n = len(s["c"])

    # ---- 1. data quality ----
    if n == 0:
        return no_trade(["no closed candles available"], data_as_of=None)
    last_close_ms = s["t"][-1] + step
    age = now.timestamp() - last_close_ms / 1000
    base.update(data_as_of=_iso(last_close_ms), data_freshness_seconds=round(age, 1))
    if n < cfg.min_bars:
        return no_trade([f"not enough history ({n} closed candles, need {cfg.min_bars})"])
    if age > cfg.max_staleness_intervals * step / 1000:
        return no_trade([f"market data is stale (last candle closed {int(age)}s ago)"])
    if gaps > cfg.max_gaps:
        return no_trade([f"{gaps} missing candles in the data (max {cfg.max_gaps})"])

    t, o, h, l, c, v = (s[k] for k in ("t", "o", "h", "l", "c", "v"))
    px = c[-1]

    # ---- 2. regime ----
    a = ind.atr(h, l, c)[-1]
    adx = ind.adx(h, l, c)["adx"][-1]
    e50 = ind.ema(c, 50)
    slope = e50[-1] - e50[-6]
    atr_pct = a / px * 100
    if atr_pct > cfg.atr_pct_volatile:
        regime = "volatile"
    elif adx >= cfg.adx_trend_min and slope > 0 and px > e50[-1]:
        regime = "trending_up"
    elif adx >= cfg.adx_trend_min and slope < 0 and px < e50[-1]:
        regime = "trending_down"
    else:
        regime = "ranging"
    htf_bias = _bias(_closed(htf_series, cfg.htf, now)) if htf_series else None
    base.update(regime=regime, htf_bias=htf_bias, atr=a, adx=adx)

    if regime == "volatile":
        return no_trade([f"volatility too high (ATR {atr_pct:.1f}% of price)"])
    if regime == "ranging":
        return no_trade([f"no clear trend (ADX {adx:.1f}, EMA50 slope {'up' if slope > 0 else 'down'})"])
    side = "LONG" if regime == "trending_up" else "SHORT"
    bull = side == "LONG"
    want = "bullish" if bull else "bearish"

    # ---- 3. strategy rules (hard requirements) ----
    smc = analyze_smc(o, h, l, c)
    supporting, conflicting = [], []
    sup = lambda f, d, w: supporting.append({"factor": f, "detail": d, "weight": w})  # noqa: E731
    con = lambda f, d, w: conflicting.append({"factor": f, "detail": d, "weight": w})  # noqa: E731
    sup("Regime", f"{'Uptrend' if bull else 'Downtrend'} on {cfg.timeframe}: ADX {adx:.1f}, price {'above' if bull else 'below'} a {'rising' if bull else 'falling'} EMA 50", 20)

    if smc["trend"] != want:
        return no_trade([f"SMC structure is {smc['trend'] or 'undefined'}, which conflicts with the {regime.replace('_', ' ')} regime"],
                        supporting=supporting)
    last_ev = smc["structure"][-1]
    sup("Market structure", f"Latest {last_ev['type']} was {want} (close through {last_ev['level']:.6g})", 15)

    zones = []
    for ob in smc["order_blocks"]:
        if ob["direction"] == want and ob["status"] != "broken" and ob["created_index"] >= n - cfg.zone_lookback:
            zones.append(("order block", ob["status"], ob["low"], ob["high"], ob["index"]))
    for g in smc["fvgs"]:
        if g["direction"] == want and g["status"] in ("open", "partial") and g["index"] >= n - cfg.zone_lookback:
            zones.append(("fair value gap", g["status"], g["low"], g["high"], g["index"]))
    if bull:
        zones = [z for z in zones if z[2] < px]                       # zone below (or containing) price
        dist = lambda z: max(0.0, px - z[3])                          # noqa: E731
    else:
        zones = [z for z in zones if z[3] > px]
        dist = lambda z: max(0.0, z[2] - px)                          # noqa: E731
    zones = [z for z in zones if dist(z) <= cfg.zone_max_dist_atr * a]
    if not zones:
        return no_trade([f"no {want} order block or fair value gap within {cfg.zone_max_dist_atr} ATR of price"], supporting=supporting)
    zone = min(zones, key=lambda z: (dist(z), -z[4]))
    kind, zstatus, zlo, zhi, zidx = zone
    entry_mid = (zlo + zhi) / 2
    stop = zlo - cfg.stop_buffer_atr * a if bull else zhi + cfg.stop_buffer_atr * a
    risk = abs(entry_mid - stop)
    sup("Entry zone", f"{zstatus.capitalize()} {want} {kind} at {zlo:.6g}–{zhi:.6g}, {dist(zone) / a:.2f} ATR from price", 10 if zstatus in ("fresh", "open") else 5)

    # targets: resting liquidity beyond entry, else R multiples
    liq = [x["level"] for x in smc["liquidity"]["levels"] if x["status"] == "resting" and x["side"] == ("BSL" if bull else "SSL")]
    liq = sorted({x for x in liq if (x > entry_mid + 0.5 * risk if bull else x < entry_mid - 0.5 * risk)}, reverse=not bull)
    targets, sources = [], []
    for lvl in liq:                                   # keep targets at least 0.5R apart
        if len(targets) == 3:
            break
        if targets and abs(lvl - targets[-1]) < 0.5 * risk:
            continue
        targets.append(lvl); sources.append(f"resting {'buy' if bull else 'sell'}-side liquidity")
    mult = 2.0
    while len(targets) < 3:
        nxt = entry_mid + mult * risk if bull else entry_mid - mult * risk
        if not targets or ((nxt - targets[-1] if bull else targets[-1] - nxt) >= 0.5 * risk):
            targets.append(nxt); sources.append(f"{mult:g}R")
        mult += 1.0

    # ---- 4. evidence ----
    if htf_bias == ("up" if bull else "down"):
        sup("Higher timeframe", f"{cfg.htf} trend agrees ({htf_bias})", 15)
    elif htf_bias in ("up", "down"):
        con("Higher timeframe", f"{cfg.htf} trend is {htf_bias}, against this {side}", 15)
    pd = smc["premium_discount"]
    if pd:
        good = "discount" if bull else "premium"
        if pd["zone"] == good:
            sup("Premium/discount", f"Price is in the {good} half of the dealing range ({pd['range_low']:.6g}–{pd['range_high']:.6g})", 10)
        elif pd["zone"] != "equilibrium":
            con("Premium/discount", f"Price is in the {pd['zone']} half of the dealing range, unfavourable for a {side}", 10)
    recent_sweeps = [x for x in smc["liquidity"]["sweeps"] if x["event_index"] >= n - 10]
    if any(x["side"] == ("SSL" if bull else "BSL") for x in recent_sweeps):
        sup("Liquidity sweep", f"{'Sell' if bull else 'Buy'}-side liquidity was swept in the last 10 candles", 10)
    if any(x["side"] == ("BSL" if bull else "SSL") for x in recent_sweeps):
        con("Liquidity sweep", f"{'Buy' if bull else 'Sell'}-side liquidity was swept recently (move may have been rejected)", 5)
    if any(i["direction"] == want and i["status"] == "taken" and i["taken_index"] >= n - 20 for i in smc["inducements"]):
        sup("Inducement", "An inducement level was taken after the structure break", 5)
    r = ind.rsi(c)[-1]
    if r is not None and (r > 70 if bull else r < 30):
        con("RSI", f"RSI {r:.1f} is in the {'overbought' if bull else 'oversold'} zone", 10)
    hist = ind.macd(c)["histogram"][-1]
    if hist is not None:
        (sup if (hist > 0) == bull else con)("MACD", f"Histogram is {'positive' if hist > 0 else 'negative'}", 5)
    vs = ind.sma(v, 20)
    bi = last_ev["index"]
    if vs[bi] and v[bi] > 1.2 * vs[bi]:
        sup("Volume", "The structure break happened on above-average volume (>1.2× 20-bar average)", 5)
    pats = [p for p in detect_candlestick_patterns(o, h, l, c) if p["index"] >= n - 3]
    pa = sum(1 for p in pats if p["bias"] == want)
    pc = sum(1 for p in pats if p["bias"] not in (want, "neutral"))
    if pa:
        sup("Candlestick patterns", ", ".join(sorted({p["pattern"] for p in pats if p["bias"] == want})) + " in the last 3 candles", min(10, 5 * pa))
    if pc:
        con("Candlestick patterns", ", ".join(sorted({p["pattern"] for p in pats if p["bias"] not in (want, "neutral")})) + " in the last 3 candles", min(10, 5 * pc))
    for f in double_tops_bottoms(h, l, c):
        if f["status"] == "confirmed" and f["confirmed_index"] >= n - 50:
            (sup if f["bias"] == want else con)("Chart formation", f"Confirmed {f['formation'].lower()} (neckline {f['neckline']:.6g})", 10)
    if market == "futures" and funding_rate is not None:
        if (funding_rate > cfg.funding_extreme) if bull else (funding_rate < -cfg.funding_extreme):
            con("Funding", f"Funding {funding_rate * 100:.4f}% suggests crowded {'longs' if bull else 'shorts'}", 5)
        elif (funding_rate < -cfg.funding_extreme) if bull else (funding_rate > cfg.funding_extreme):
            sup("Funding", f"Funding {funding_rate * 100:.4f}% leans against the crowd", 5)

    score = max(0, min(100, sum(x["weight"] for x in supporting) - sum(x["weight"] for x in conflicting)))

    # ---- 5. risk / reward after costs ----
    fee = cfg.fee_rate.get(market, max(cfg.fee_rate.values()))
    cost = entry_mid * 2 * (fee + cfg.slippage)
    gross_rr = abs(targets[0] - entry_mid) / risk
    net_rr = (abs(targets[0] - entry_mid) - cost) / (risk + cost)
    base.update(score=score, supporting=supporting, conflicting=conflicting)

    reasons = []
    if score < cfg.min_score:
        reasons.append(f"heuristic score {score} is below the minimum {cfg.min_score}")
    if net_rr < cfg.min_rr:
        reasons.append(f"reward:risk to TP1 after costs is {net_rr:.2f}, below the minimum {cfg.min_rr}")
    if reasons:
        return no_trade(reasons, candidate_side=side, entry_low=zlo, entry_high=zhi, stop=stop, targets=targets,
                        rr=round(gross_rr, 2), rr_net=round(net_rr, 2))

    # ---- 6. emit ----
    zone_time = _iso(t[zidx])
    invalid = (f"A {cfg.timeframe} close {'below' if bull else 'above'} {stop:.6g}, or the {kind} at {zlo:.6g}–{zhi:.6g} "
               f"being broken, or no entry within {cfg.expiry_bars} candles")
    explanation = (f"{side} {symbol} ({market}) on {cfg.timeframe}: {regime.replace('_', ' ')} with {want} structure; "
                   f"price is near {'an' if zstatus[0] in 'aeiou' else 'a'} {zstatus} {want} {kind}. Entry {zlo:.6g}–{zhi:.6g}, stop {stop:.6g}, "
                   f"targets {', '.join(f'{x:.6g}' for x in targets)}. Net reward:risk to TP1 ≈ {net_rr:.2f} after assumed costs.")
    return {
        **base, "side": side, "lifecycle": "active", "reasons": [],
        "entry_logic": f"Limit entry inside the {zstatus} {want} {kind} formed at {zone_time}",
        "entry_low": zlo, "entry_high": zhi, "stop": stop, "targets": targets, "target_sources": sources,
        "rr": round(gross_rr, 2), "rr_net": round(net_rr, 2), "invalidation": invalid, "explanation": explanation,
        "assumptions": {"fee_rate_per_side": fee, "slippage_per_side": cfg.slippage, "funding_rate": funding_rate,
                        "note": "Costs are estimates. Leverage magnifies losses. Funding is not included in reward:risk."},
        "expires_at": (now + timedelta(milliseconds=cfg.expiry_bars * step)).isoformat(),
        "fingerprint": f"{symbol}|{market}|{cfg.timeframe}|{side}|{cfg.name}@{cfg.version}|{zone_time}",
    }
