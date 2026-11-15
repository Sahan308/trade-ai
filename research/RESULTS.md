# v1.1 research results

**Outcome: no candidate met the pre-registered eligibility rules, so no v1.1 is released.** As the protocol requires, the holdout year (2025-11-15 → 2026-11-14) was **not evaluated** and stays untouched for a future, separately pre-registered round.

Protocol: [`PROTOCOL.md`](PROTOCOL.md), committed in `c0cf25a` before any candidate was run. Raw numbers: [`design_results.json`](design_results.json). Harness: [`run_v11.py`](run_v11.py).

## Design period: 2023-11-15 → 2025-11-14, 8 spot symbols, 1H, pooled

| Candidate | Trades | Win rate | Profit factor | Expectancy | Total | Walk-forward trades | Walk-forward expectancy | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| v1.0.0 (baseline) | 2,808 | 24.4% | 0.67 | −0.332R | −931.2R | 1,484 | −0.313R | (reference) |
| A: stop ≥ 1 ATR | 2,280 | 30.4% | 0.79 | −0.166R | −378.6R | 1,116 | −0.139R | no |
| B: stop ≥ 1.5 ATR | 1,771 | 34.6% | 0.84 | −0.113R | −199.4R | 695 | −0.172R | no |
| C: A + 4H agreement | 2,139 | 30.6% | 0.79 | −0.166R | −355.7R | 1,007 | −0.190R | no |
| D: B + 4H agreement | 1,677 | 34.1% | 0.81 | −0.129R | −217.1R | 699 | −0.172R | no |
| E: C + R-multiple targets | 0 | — | — | — | — | 0 | — | no (see flaw) |
| F: D + R-multiple targets | 0 | — | — | — | — | 0 | — | no (see flaw) |
| G: C + risk ≥ 10× costs | 100 | 24.0% | 0.33 | −0.502R | −50.2R | 71 | −0.529R | no |

Every candidate lost money on all 8 symbols in the design period. Per-symbol totals are in `design_results.json`.

## What this shows
- **The 1H SMC pullback idea does not have a positive edge here** after realistic spot costs (0.10% fee + 0.05% slippage per side, stop first on same-candle collisions).
- **Wider stops help but don't fix it.** Moving the stop to at least 1–1.5 ATR raised the win rate from 24% to 30–35% and roughly halved the loss per trade, but expectancy stayed negative in-sample and in walk-forward.
- **Requiring 4H agreement (C, D) did not help** compared with the same stop rule without it (A, B).
- **The cost filter (G) left few trades**, and those performed worst. Stops wide enough to dwarf costs on 1H were rare and not better.

## Flaw in the protocol (my error)
Candidates **E and F could never trade**. Their first target was 1.5R, but the fixed minimum net reward:risk to TP1 is also 1.5 *after costs*, which a 1.5R target can never reach. This was a design mistake in the candidate list, not a market finding. It doesn't change the outcome, because no other candidate came close to eligibility. Any future round must check that each candidate can actually produce trades before it's registered.

## Limits of this study
- Spot only, 1H only, one strategy family, taker costs.
- No 1-minute data, so same-candle collisions used the conservative stop-first rule.
- Market regimes from late 2023 to late 2025 only.

## Decision
- v1.0.0 remains the code default, but it's flagged in the app as **experimental with negative backtest results**. It should not be sold as a signal service on this evidence.
- The holdout year is still unused and can serve a future round with a **new, separately pre-registered** hypothesis (for example 4H/1D swing setups where costs are a smaller share of each move, or maker-fee entries).

---

# Round 2 results: 4H swing variants

**Outcome: no candidate met the pre-registered eligibility rules, so nothing is released.** The holdout year is **still unused**.

Protocol: [`PROTOCOL_R2.md`](PROTOCOL_R2.md), committed in `1e64867` before any round-2 candidate was run. Raw numbers: [`design_results_r2.json`](design_results_r2.json). Harness: [`run_r2.py`](run_r2.py).

## Design period: 2023-11-15 → 2025-11-14, 8 spot symbols, 4H decisions with 1D context, pooled

| Candidate | Trades | Win rate | Profit factor | Expectancy | Total | Walk-forward trades | Walk-forward expectancy | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| S0: swing profile as is | 618 | 19.9% | 0.71 | −0.265R | −163.7R | 396 | −0.163R | no |
| S1: stop ≥ 1 ATR | 467 | 25.7% | 0.70 | −0.237R | −110.9R | 317 | −0.210R | no |
| S2: stop ≥ 1.5 ATR | 264 | 29.5% | 0.76 | −0.170R | −44.9R | 183 | −0.280R | no |
| S3: S1 + 1D agreement | 421 | 25.7% | 0.71 | −0.229R | −96.5R | 269 | −0.291R | no |
| S4: S2 + 1D agreement | 240 | 30.8% | 0.76 | −0.163R | −39.2R | 193 | −0.279R | no |
| S5: S1, min R:R 1.5 | 581 | 28.6% | 0.77 | −0.168R | −97.5R | 317 | −0.210R | no |
| S6: S1, 2/3/4R targets, min R:R 1.5 | 591 | 33.7% | 0.78 | −0.142R | −84.2R | 392 | −0.118R | no |

All candidates could trade (the feasibility check passed). Every candidate's pooled design result was negative, and almost every symbol was negative for every candidate. The only exceptions were small positives on SOL (S1, S3, S5) and ADA (S4), which isn't a consistent pattern.

## What this shows
- Moving to 4H reduced how much costs hurt (losses per trade are smaller than on 1H), but the **pullback-to-order-block/FVG idea still has no positive edge** on these 8 coins over these 2 years.
- Across both rounds (15 candidates, 1H and 4H), the best walk-forward expectancy was −0.118R per trade.

## Decision
- Stop iterating on this strategy family against the same design period. More variants would mostly fit noise (data snooping).
- Keep v1.0.0 flagged as experimental in the app with these findings. Don't sell it as a signal service.
- The holdout year remains untouched, available for a genuinely new idea with its own pre-registered protocol.

---

## Round 3: different strategy families (pre-registered in `PROTOCOL_R3.md`, commit 8437eec)

Six long-only spot candidates on the same 8 symbols, with costs of 0.15% per side and next-open fills: Donchian breakouts T1 (20/10) and T2 (55/20), a trend filter T3 (close vs SMA 100), an MA crossover T4 (50/200), RSI(2) reversion M1, and Bollinger reversion on 4H M2.

### Design period (2023-11-15 → 2025-11-14)
| id | trades | win rate | mean / trade | profit factor | half-years positive | eligible |
|---|---|---|---|---|---|---|
| **T1** | 99 | 36% | **+5.9%** | 2.04 | 3 of 4 | **yes (chosen)** |
| T2 | 45 | 36% | +7.3% | 2.27 | 4 of 4 | no (under 60 trades) |
| T3 | 138 | 17% | +3.1% | 1.84 | 3 of 4 | yes |
| T4 | 16 | 31% | +4.4% | 1.22 | 1 of 3 | no |
| M1 | 107 | 59% | +0.2% | 1.11 | 2 of 3 | no |
| M2 | 283 | 50% | −0.6% | 0.74 | 0 of 4 | no |

Equal-weight buy-and-hold over the design window: +116% (1D) / +107% (4H). This was a strong bull market. Design results were committed (d427c5b) before the holdout was run.

### Holdout (2025-11-15 → 2026-11-14), run once, for T1 only
| trades | win rate | mean / trade | profit factor | max symbol share of gross profit | result |
|---|---|---|---|---|---|
| 43 | 23% | **−2.0%** | **0.64** | 25% | **FAIL** |

Equal-weight buy-and-hold over the holdout year: **−42%**.

**Conclusion.** The 20-day breakout's design-period edge did not survive the out-of-sample year. In a falling market it lost far less than holding, but it still lost money, so it fails the pre-registered criteria and won't be released as a signal strategy. The holdout year has now been used. Any future round needs fresh, unseen data, for example evaluated forward in time. Across three rounds and 21 variants, no strategy has passed.
