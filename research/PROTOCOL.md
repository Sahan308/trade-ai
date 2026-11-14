# Strategy research protocol: smc_trend_pullback v1.1

Written and committed **before** any v1.1 variant was evaluated. The point is to stop the results from shaping the rules after the fact.

## Why
The v1.0.0 backtest (BTCUSDT 1H, Aug–Nov 2026) lost: 34 trades, expectancy −1.22R, profit factor 0.23. Average losses were bigger than 1R, which means the stop sat too close to entry relative to round-trip costs.

## Data
- Binance **spot** 1H candles (4H for higher-timeframe context), public data, downloaded 2026-11-14.
- Symbols (fixed): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, LINKUSDT, AVAXUSDT.
- Range: 2023-11-15 → 2026-11-14 (26,280 hourly candles each, no gaps).

## Periods
- **Design period:** 2023-11-15 → 2025-11-14 (2 years). All variant comparison and selection happens here only.
- **Holdout period:** 2025-11-15 → 2026-11-14 (1 year). Evaluated **once**, only for the single variant chosen on the design period and for v1.0.0 as a reference. No changes after seeing it.

## Fixed costs and rules
- Fee 0.10% and slippage 0.05% per side (spot, from v1.0.0). No funding (spot).
- Same-candle stop/target collisions: **stop first**. There's no 1-minute data here, so this is conservative.
- Fills, exits, one position at a time, latency 0: unchanged from Milestone 6.

## Candidates (complete list, decided now)
| id | stop_min_atr | htf_required | targets | min_risk_cost_ratio |
|---|---|---|---|---|
| v1.0.0 (baseline) | 0 | no | liquidity | 0 |
| A | 1.0 | no | liquidity | 0 |
| B | 1.5 | no | liquidity | 0 |
| C | 1.0 | yes | liquidity | 0 |
| D | 1.5 | yes | liquidity | 0 |
| E | 1.0 | yes | R-multiples 1.5/2.5/3.5 | 0 |
| F | 1.5 | yes | R-multiples 1.5/2.5/3.5 | 0 |
| G | 1.0 | yes | liquidity | 10 |

- `stop_min_atr`: the stop is at least this many ATRs from the middle of the entry zone.
- `htf_required`: the 4H trend must agree (otherwise NO TRADE).
- `min_risk_cost_ratio`: risk per unit must be at least this many times the round-trip cost (otherwise NO TRADE).
- Score and reward:risk thresholds stay at v1.0.0 values (min score 60, min net reward:risk 1.5).

## Selection (design period only)
For each candidate, pool the trades from all 8 symbols:
1. **Walk-forward inside the design period**, using the Milestone 6 method per symbol. The pooled walk-forward test-window expectancy is the **primary** criterion.
2. **Eligibility:** at least 100 pooled design-period trades, design-period profit factor ≥ 1.0, and walk-forward expectancy > 0.
3. Choose the eligible candidate with the highest walk-forward expectancy. If none is eligible, **no v1.1 is released** and the research stops here.

## Holdout pass criteria (decided now)
The chosen candidate passes only if, on the holdout year, pooled across the 8 symbols:
- at least 50 trades,
- expectancy > 0R after costs,
- profit factor ≥ 1.1,
- no single symbol contributes more than 50% of the total positive R.

If it fails, v1.1 is **not** made the default, and the result is reported as is.

## Reporting
Every candidate's design-period numbers and the holdout result are published in `research/RESULTS.md`, including failures.
