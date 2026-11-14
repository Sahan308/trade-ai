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
