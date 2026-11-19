# Round 5 protocol (written before any results)

Ten signal systems, each with fixed textbook rules and NO parameter tuning (see run_r5.py).
20 large coins, Binance spot, closed candles only, entry at the next bar's open, 0.15% round-trip cost.

Two periods: A = 2020-2023, B = 2024-01-01 to 2026-11-19.
Caveat: neither period is untouched — earlier rounds looked at this history. That is why there is no tuning,
and why passing systems must ALSO pass a live forward paper test before they go on the website.

A system PASSES only if, in BOTH periods: >= 100 trades, average >= +0.10R per trade after costs,
profit factor >= 1.2, and the t-statistic of monthly R sums >= 2.0 (monthly grouping because trades cluster).

## Result of the history test (2026-11-19)
No system passed. The four breakout systems (S1, S2, S3, S9) made money in both periods
(2024-26: +0.30 to +0.72R per trade, profit factor 1.5-2.5), but their monthly results were too uneven to
pass the t >= 2 rule in 2024-26. The other six were flat or losing in 2024-26.
These four, frozen as written, go into the live paper test (`run_r5.py forward`), trades entering on or after 2026-11-19.
