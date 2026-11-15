# Strategy research protocol, round 3: different strategy families

Written and committed **before** any round-3 candidate was evaluated. Rounds 1 and 2 (SMC trend-pullback on 1H and 4H, 15 variants) all failed; see `RESULTS.md`.

## Hypothesis
The SMC pullback logic may simply have no edge after costs. Round 3 tests well-known, simple strategy families from the trend-following and mean-reversion literature on the same data. All candidates are long-only spot, so no funding costs and no shorting.

## Data
- Binance spot **1D** candles (the 4H set for M2), the same 8 symbols as rounds 1–2: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, LINKUSDT, AVAXUSDT.
- Same files as rounds 1–2 (`research-data` branch). History starts around 2023-11-15, so long lookbacks (SMA 200) only become usable about 200 days into the design period. No trades are opened before an indicator has its full lookback.

## Periods (unchanged)
- **Design:** 2023-11-15 → 2025-11-14. All comparison and selection happens here.
- **Holdout:** 2025-11-15 → 2026-11-14. Still unused. Evaluated **once**, only for the candidate chosen here. If no candidate is eligible, the holdout stays unused.

## Costs and execution
- Fee 0.10% and slippage 0.05% per side.
- Signals are computed on a **closed** candle, and orders fill at the **next candle's open**.
- Protective stops (where defined) fill at the stop price, or at the open if the market gaps through it. When a stop and an exit signal happen on the same candle, the stop counts first.
- One position at a time per symbol, full position size. Returns are per trade, net of costs.

## Candidates (complete list, decided now)
| id | family | entry (on close) | exit | stop |
|---|---|---|---|---|
| T1 | Donchian breakout | close > highest high of previous 20 days | close < lowest low of previous 10 days | 2 × ATR(20) below entry |
| T2 | Donchian breakout (Turtle) | close > highest high of previous 55 days | close < lowest low of previous 20 days | 2 × ATR(20) |
| T3 | Trend filter | close > SMA(100) | close < SMA(100) | none |
| T4 | MA crossover | SMA(50) crosses above SMA(200) | SMA(50) crosses below SMA(200) | none |
| M1 | RSI(2) reversion | RSI(2) < 10 and close > SMA(200) | close > SMA(5), or 10 days held | none |
| M2 | Bollinger reversion, 4H | close < lower band(20, 2) and close > SMA(200) | close ≥ middle band, or 30 candles held | 2 × ATR(14) |

## Design-period evaluation
For each candidate, pooled across the 8 symbols:
- trade count, win rate, mean net return per trade, profit factor (gross wins ÷ gross losses), total compounded return per symbol;
- **stability:** the design period is split into four consecutive half-years, and the mean trade return is computed in each;
- **benchmark:** equal-weight buy-and-hold over the same tradable window, reported for context only.

**Eligibility:** all of these must hold:
1. at least **60** pooled trades;
2. profit factor at least **1.2**;
3. mean net return per trade above 0;
4. positive mean trade return in at least **3 of the 4** half-years that contain trades.

**Selection:** the eligible candidate with the highest mean net return per trade. If none is eligible, round 3 ends with no release, and the holdout stays unused.

## Holdout pass criteria
Pooled across the 8 symbols in the holdout year:
- at least **30** trades;
- mean net return per trade above 0;
- profit factor at least **1.1**;
- no single symbol contributing more than **50%** of the gross profit.

Buy-and-hold over the holdout year is reported alongside for context.

## What a pass would and wouldn't mean
A pass means one year of out-of-sample evidence, on 8 spot symbols, under these cost assumptions. It doesn't prove future profitability. The app would describe it exactly that way, with the numbers and sample size, and as a long-only, low-frequency strategy. A fail is published in full.
