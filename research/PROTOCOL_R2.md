# Strategy research protocol, round 2: 4H swing variants of smc_trend_pullback

Written and committed **before** any round-2 candidate was evaluated. Round 1 (1H) failed; see `RESULTS.md`.

## Hypothesis
On 1H, round-trip costs (~0.3%) were a large share of the stop distance, and all variants lost. On **4H**, typical moves and ATR are several times larger, so costs are a smaller share of each trade. The same pullback logic might then have a positive edge after costs.

## Data
- Binance spot 4H candles for decisions, 1D for higher-timeframe context. Public data, downloaded 2026-11-14.
- Symbols (fixed, same as round 1): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, LINKUSDT, AVAXUSDT.

## Periods (same as round 1)
- **Design period:** 2023-11-15 → 2025-11-14. All comparison and selection happens here.
- **Holdout period:** 2025-11-15 → 2026-11-14. Still unused after round 1. Evaluated **once**, only for the candidate chosen here (with v1.0.0's swing profile S0 as reference). No changes after seeing it. If round 2 also fails to produce an eligible candidate, the holdout stays unused.

## Fixed costs and rules
- Fee 0.10% and slippage 0.05% per side (spot). No funding.
- Stop first on same-candle collisions (no 1-minute data). Latency 0. One position at a time per symbol.
- Base settings: the existing `swing` profile (4H decisions, 1D context, min score 60, min net reward:risk 2.0, zone lookback 80, expiry 10 candles, time exit after 40 candles in the trade).

## Candidates (complete list, decided now)
| id | stop_min_atr | htf_required | targets | min net reward:risk |
|---|---|---|---|---|
| S0 (swing profile as is) | 0 | no | liquidity | 2.0 |
| S1 | 1.0 | no | liquidity | 2.0 |
| S2 | 1.5 | no | liquidity | 2.0 |
| S3 | 1.0 | yes | liquidity | 2.0 |
| S4 | 1.5 | yes | liquidity | 2.0 |
| S5 | 1.0 | no | liquidity | 1.5 |
| S6 | 1.0 | no | R-multiples 2/3/4 | 1.5 |

**Feasibility check (lesson from round 1):** S6's 2R first target can pass a 1.5 net reward:risk minimum whenever risk is at least 5× the round-trip cost. On 4H with a stop of at least 1 ATR, that's normal. Any candidate that still produces **zero** design-period trades is reported as *infeasible* and excluded. That check looks only at trade counts, never at returns.

## Selection (design period only)
Same as round 1, applied to S0–S6 pooled across the 8 symbols:
1. The primary criterion is pooled **walk-forward** test-window expectancy (Milestone 6 method, per symbol).
2. **Eligibility:** at least 100 pooled design-period trades, design-period profit factor ≥ 1.0, and walk-forward expectancy > 0.
3. Choose the eligible candidate with the highest walk-forward expectancy. If none is eligible, round 2 ends with no release.

## Holdout pass criteria (unchanged from round 1)
On the holdout year, pooled across the 8 symbols, the chosen candidate needs:
- at least 50 trades,
- expectancy > 0R after costs,
- profit factor ≥ 1.1,
- no single symbol contributing more than 50% of the total positive R.

## What a pass would and wouldn't mean
A pass means one year of out-of-sample evidence, on 8 spot symbols, under these cost assumptions. It wouldn't be proof of future profitability. The app would then describe it exactly that way, with the numbers and sample size. A fail is reported in full, just like round 1.
