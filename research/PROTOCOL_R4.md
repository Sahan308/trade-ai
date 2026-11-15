# Strategy research protocol, round 4: evidence-based portfolio trend-following

Written and committed **before** any round-4 data was downloaded or any candidate evaluated. Rounds 1–3 (21 variants) all failed; see `RESULTS.md`.

## Why this design (research basis)
- In crypto, evidence for **time-series momentum** (trend-following) is strong, while evidence for **cross-sectional momentum** (ranking coins against each other) is weak once realistic costs are applied (Han, Kang & Ryu, "Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market…").
- Zarattini, Pagani & Barbon (2025), "Catching Crypto Trends" (Swiss Finance Institute RP 25-80), report positive net results for a **long-only ensemble of Donchian breakout models** across lookbacks of 5–360 days, with **25% volatility targeting**, on a rotating universe of the 20 most liquid coins.
- Funding rates showed little reliable predictive power for price in the sources reviewed, so they are not used.
- Published results like these are usually optimistic (data mining, selection, survivorship). We therefore re-test the idea independently, on data unseen by any earlier round, with our own costs and pre-set pass rules.

## Data
- Binance spot **1D** candles. The fixed list of 25 USDT pairs, chosen now for liquidity history and not for returns:
  BTC, ETH, BNB, XRP, ADA, DOGE, LTC, LINK, TRX, XLM, ETC, BCH, EOS, ATOM, XTZ, NEO, VET, ZEC, DASH, QTUM, SOL, DOT, AVAX, UNI, FIL.
- History is downloaded from 2018-01-01. Pairs Binance no longer serves are dropped and listed in the results.
- **Survivorship bias:** delisted coins such as LUNA and FTT cannot be included, and that biases results **upward**. This is stated next to every number.

## Universe rule (point-in-time, no look-ahead)
On each day, a pair is tradable only if it has at least **365 days of history** up to that day. Among tradable pairs, the **20 with the highest median daily quote volume** (close × volume) over the previous 30 days are eligible.

## Periods
- **Warm-up:** 2018-01-01 → 2019-12-31. Indicators only, no evaluation.
- **Design:** 2020-01-01 → 2021-12-31. Comparison and selection happen here only.
- **Holdout (unseen):** 2022-01-01 → 2023-11-14. A bear market followed by a recovery. Evaluated **once**, only for the chosen candidate.
- 2023-11-15 → 2026-11-14 was used by rounds 1–3. Results on it are reported as **"already-seen context"** and are not evidence.

## Mechanics (all candidates)
- Signals use the **daily close**, and portfolio changes execute at the **next day's open**.
- **Costs:** 0.10% fee + 0.05% slippage = **0.15% on every unit of notional traded**, with no leverage.
- **Weights:** total long weight is capped at **100%** of equity, and the rest is held as cash at 0% interest. Long-only, spot.
- **Rebalancing band:** a position is changed only when its target weight differs from its current weight by more than **20% of the target** (relative), or when it opens or closes. This reduces cost churn.

## Candidates (complete list, decided now)
| id | description |
|---|---|
| **E1** | Ensemble Donchian trend (Zarattini-style). For each eligible coin and each lookback L ∈ {5, 10, 20, 30, 60, 90, 150, 250, 360}, a sub-signal turns ON when the close exceeds the highest close of the previous L days. It turns OFF when the close falls below a trailing stop, which starts at the midpoint of the highest and lowest closes over L and never moves down. Coin score = the fraction of the 9 sub-signals that are ON. Raw weight = score × (25% ÷ annualised 90-day volatility), capped at 1.0 per coin. The portfolio is scaled so the total is at most 100%, and each coin is capped at 1/N of the portfolio, with N = 20. |
| **E2** | E1 without volatility targeting: raw weight = score, then the same caps and scaling. |
| **E3** | E1 plus a **BTC regime filter**: when BTC's own E1 score is below 0.5, all target weights are halved. |
| **E4** | Simple time-series momentum: hold each eligible coin whose **90-day return is positive**, weighted by 25% ÷ volatility, with the same caps. |

**Benchmarks (context only):** BTC buy-and-hold, and an equal-weight buy-and-hold of the eligible universe rebalanced monthly. Both use the same costs on rebalances.

## Metrics
Computed from daily portfolio equity: CAGR, annualised Sharpe (daily returns × √365, risk-free 0), maximum drawdown, exposure (average total weight) and turnover.

## Design-period eligibility and selection
**Eligible** if all of these hold:
1. CAGR above 0;
2. Sharpe of at least **1.0**;
3. maximum drawdown no worse than **−40%**;
4. average daily exposure of at least 10%.

**Chosen:** the eligible candidate with the **highest Sharpe**. If none is eligible, round 4 ends with no release and the holdout stays unused.

## Holdout pass criteria (2022-01-01 → 2023-11-14, one run)
All must hold:
- CAGR above **0** net of costs;
- Sharpe at least **0.5**;
- maximum drawdown no worse than **−35%**;
- maximum drawdown smaller than the equal-weight buy-and-hold benchmark's.

## If it passes
The app may offer the chosen model as a **portfolio trend indicator**, showing which coins the model is "in trend" for and with what weight. It will be published with these exact numbers, the survivorship caveat, a **live paper-tracking period of at least 3 months** before any wording beyond "experimental", and no profit promises. A fail is published in full.
