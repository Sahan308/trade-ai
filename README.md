# TRADE-AI

Explainable crypto market analysis and decision support for Spot and Futures.
**Analysis only:** TRADE-AI never places trades, never asks for exchange API keys or trading permissions, never promises profit, and never presents a heuristic score as a win probability.

Live site (static frontend): https://sahan308.github.io/trade-ai/

## Repository layout

    index.html, app.html        Static frontend (landing page + app shell), served by GitHub Pages
    assets/css/                 Design tokens and styles
    assets/js/
      config.js                 Public, non-secret runtime config (API URLs, pricing placeholders)
      core.js, components.js    Icons, formatting, scroll reveal, modal, signal card, candlestick chart
      hero-chart.js             Landing-page chart animation (sample data only)
      providers/binance.js      Browser adapter for Binance public market data (REST + WebSocket)
      providers/hyperliquid.js  Futures fallback adapter (used only when Binance Futures is blocked/unreachable)
      services/                 marketData.js, signals.js, health.js — what the UI calls
      analysis/ta.js            Indicators, candlestick patterns, formations (JS twin of backend/app/analysis)
      analysis/smc.js           Smart Money Concepts (JS twin of backend/app/analysis/smc.py)
      analysis/risk.js          Position sizing (JS twin of backend/app/risk/sizing.py)
      fixtures/demo.js          Isolated, labelled sample data (demo mode only)
    backend/                    FastAPI service (Milestone 1)
      app/main.py               App factory: CORS allowlist, request IDs, security headers, error handlers
      app/config.py             Settings from TRADEAI_* environment variables / .env
      app/db.py, app/models.py  SQLAlchemy 2.0 engine/session + models (audit_logs)
      app/api/health.py         GET /health
      app/api/markets.py        Market data endpoints
      app/providers/            Provider-neutral types, Binance adapter, Hyperliquid futures fallback, fallback wrapper
      app/streams.py            Shared upstream WebSocket hub (reconnect, stale detection, reconciliation)
      app/api/streams.py        /ws/chart and /ws/market endpoints
      app/services/candles.py   Candle validation (malformed rows, duplicates, gaps)
      app/analysis/             indicators.py, patterns.py, summary.py: formulas documented in docstrings
      app/analysis/smc.py       BOS/CHOCH, order blocks, FVGs, liquidity & sweeps, premium/discount, inducement
      app/signals/              strategy.py (versioned configs), engine.py (pipeline), store.py (insert-only persistence)
      app/scan.py               Scanner: python -m app.scan [--loop SECONDS] [--profile day|swing|scalp]
      app/api/analysis.py       /api/analysis and /api/patterns
      app/api/signals.py        /api/signals, /api/signals/history, /api/signals/{id}
      app/risk/sizing.py        Position sizing with fees, slippage, lot/tick rounding, leverage, liquidation estimate, funding
      app/signals/lifecycle.py  Deterministic lifecycle tracking (conservative same-candle rule)
      app/signals/tracker.py    Applies lifecycle to stored signals, appends events, raises in-app alerts
      app/api/risk.py           /api/markets/{symbol}/specs, /api/risk/size
      app/api/alerts.py         /api/alerts, /api/signals/{id}/events
      app/backtest/core.py      Backtest engine, metrics, chronological splits, walk-forward
      app/backtest/__main__.py  CLI: python -m app.backtest --symbol BTCUSDT --market spot --days 180
      app/api/performance.py    /api/performance, /api/backtests, /api/backtests/{id}
      app/ratelimit.py          Per-IP rate limit (in-memory, or Redis when TRADEAI_REDIS_URL is set)
      scripts/smoke_live.py     Live check against real public data (used in CI)
      app/errors.py             Consistent JSON error envelope
      migrations/               Alembic migrations (0001: audit_logs)
      tests/                    pytest suite
    docker-compose.yml          Local Postgres + API
    .github/workflows/ci.yml    Runs backend tests (SQLite + Postgres migrations) and JS syntax checks

## Run locally

### Frontend
No build step.

    python3 -m http.server 8080
    # http://localhost:8080            landing page
    # http://localhost:8080/app.html   app shell (add ?demo=1 for the labelled sample preview)

To show the API status in the app sidebar, set `api.backendBaseUrl` in `assets/js/config.js` (e.g. `"http://localhost:8000"`).

### Backend (Python 3.12+)

    cd backend
    python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements-dev.txt
    cp .env.example .env                                     # SQLite by default
    alembic upgrade head
    uvicorn app.main:app --reload --port 8000
    # http://localhost:8000/health   http://localhost:8000/docs (disabled in production)

Run the tests:

    cd backend && pytest

### Backend with Postgres (Docker)

    docker compose up --build
    # API on http://localhost:8000, Postgres on localhost:5432 (local dev credentials only)

## Configuration (backend)

| Variable | Default | Notes |
|---|---|---|
| `TRADEAI_ENV` | `development` | `development`, `test` or `production`. Production disables `/docs` and adds HSTS. |
| `TRADEAI_DATABASE_URL` | `sqlite:///./tradeai.db` | Postgres: `postgresql+psycopg://user:pass@host:5432/db` |
| `TRADEAI_CORS_ORIGINS` | `http://localhost:8080` | Comma-separated; `*` is rejected in production |
| `TRADEAI_LOG_LEVEL` | `INFO` | |
| `TRADEAI_BINANCE_SPOT_BASE` | `https://data-api.binance.vision` | Public market-data mirror |
| `TRADEAI_BINANCE_FUTURES_BASE` | `https://fapi.binance.com` | USDT-M Futures |
| `TRADEAI_MARKETS` | `BTCUSDT:spot,ETHUSDT:spot,SOLUSDT:futures,BNBUSDT:spot,XRPUSDT:futures` | Listed by `/api/markets` |
| `TRADEAI_FUTURES_FALLBACK_BASE` | `https://api.hyperliquid.xyz` | Futures fallback; empty string disables it |
| `TRADEAI_RATE_LIMIT_PER_MINUTE` | `120` | Per client IP, for `/api/*` requests and WebSocket connection attempts |
| `TRADEAI_REDIS_URL` | unset | Set it (e.g. `redis://localhost:6379/0`) to share rate limits across processes and servers. Without it, limits are per process. If Redis goes down, requests are allowed and a warning is logged. |
| `TRADEAI_WS_MAX_PER_IP` | `10` | Concurrent WebSocket connections per IP (per process) |

Secrets belong in environment variables or `.env` (git-ignored), never in `assets/js/config.js`.

## API (implemented endpoints only)

`GET /health` → `200` when healthy, `503` when the database is unreachable.

```json
{ "status": "ok", "version": "0.1.0", "environment": "development",
  "time_utc": "2026-11-14T10:00:00Z", "components": { "database": { "status": "ok", "error": null } } }
```

Errors use one envelope: `{"error": {"code": "not_found", "message": "...", "request_id": "..."}}`. Every response carries `X-Request-ID`. Internal error details are logged, never returned.

| Endpoint | Description |
|---|---|
| `GET /api/markets` | Configured symbols and provider |
| `GET /api/markets/{symbol}/candles?market=spot\|futures&interval=1m\|5m\|15m\|1H\|4H\|1D&limit=1..1000` | Validated candles (UTC), plus `gaps`, `dropped`, `source`, `fetched_at` |
| `GET /api/markets/{symbol}/ticker?market=spot\|futures` | Last price, 24h change and quote volume, `data_time`, `source` |
| `GET /api/futures/{symbol}/funding` | Futures **mark** and **index** price, funding rate and next funding time |

Provider failures map to `502` (provider down or bad payload), `503` (rate limited or region blocked, with `Retry-After`) or `400`. Responses are cached for 5–10s, and the adapter stops before Binance's per-minute request-weight limit.

Ticker responses include `price_label` and funding responses include `index_label`, because the fallback venue reports a mid price and an oracle price rather than a last trade and an index.

### WebSockets

| Endpoint | Events |
|---|---|
| `WS /ws/chart/{symbol}/{interval}?market=spot\|futures` | `status`, `candle` (`closed` true when the candle is final), `snapshot` (recent candles over REST after each upstream reconnect) |
| `WS /ws/market/{symbol}` | `status`, `funding` (mark and index/oracle price, funding rate, next funding time) |

All browsers watching the same stream share one upstream connection. The hub reconnects with backoff, reports `stale` after 30s without data, and closes the upstream when the last viewer leaves. Connections are checked against the CORS origin list and the rate limit.

### Analysis endpoints

| Endpoint | Description |
|---|---|
| `GET /api/analysis/{symbol}?market&interval&limit=60..1000` | Latest readings for every indicator, volume profile, Fibonacci, pivots, patterns in the last 30 candles, formations, swing points |
| `GET /api/patterns/{symbol}?market&interval&window&bias=bullish\|bearish\|neutral` | Candlestick patterns (with the indices of the candles that triggered them) and chart formations |

### Signal endpoints

| Endpoint | Description |
|---|---|
| `GET /api/signals?symbol&side=LONG\|SHORT&limit` | Recent LONG/SHORT signals |
| `GET /api/signals/history?offset&limit&side` | Every stored evaluation, including NO TRADE, newest first, with a total count |
| `GET /api/signals/{id}` | One signal with all its evidence, assumptions and the strategy-config snapshot |

Signals are created by the scanner, not by API calls. Each scanner pass also runs lifecycle tracking.

### Risk, lifecycle and alert endpoints

| Endpoint | Description |
|---|---|
| `GET /api/markets/{symbol}/specs?market` | Tick size, lot step, minimum quantity and order value, maintenance-margin rate (Futures) |
| `GET /api/risk/size?balance&risk_pct&entry&stop&side&market&leverage&fee_rate&slippage&hold_hours&symbol` | Position size. With `symbol`, exchange specs and the current funding rate are applied |
| `GET /api/signals/{id}/events` | Lifecycle events and the simulated outcome |
| `GET /api/alerts?after_id&limit` | In-app alerts, newest first |

### Performance endpoints

| Endpoint | Description |
|---|---|
| `GET /api/performance?kind=prospective\|backtest\|paper&risk_pct` | Measured results for one kind only. Kinds are never mixed. `paper` reports "not available" |
| `GET /api/backtests` | Stored backtest runs (summaries) |
| `GET /api/backtests/{id}` | Full run: assumptions, full period, chronological splits, walk-forward folds, trades, equity curve |

## Backtesting and performance (Milestone 6)

Run a backtest on real history (stored in the database and shown on the History page):

    cd backend && python -m app.backtest --symbol BTCUSDT --market spot --days 180
    # options: --market futures --profile swing --latency 1 --funding 0.0001 --risk 1 --no-1m --no-store

- **No look-ahead or repainting:** at each closed candle the engine is called on data that ends at that candle. A test checks that adding future data never changes earlier decisions. Entries are only possible on later candles, and `--latency` adds more delay.
- **Fills and exits:** the same lifecycle rules as live signals (worse-edge fills, thirds at TP1/2/3, time exit). Same-candle stop/target collisions are replayed on **1-minute candles**. If the order is still unclear, the stop is assumed first. Collisions are counted in the results.
- **Costs:** fee and slippage per side from the strategy config, plus Futures funding at an assumed rate per 8h (default 0.01%) for the time held.
- **One position at a time.** Trades still open when the data ends aren't counted. Each period below is simulated on its own, so trade counts across periods can differ slightly from the full-period run.
- **Chronological splits:** 60% development, 20% validation, 20% **out-of-sample** (untouched; nothing tuned on it).
- **Walk-forward:** on each rolling training window, the minimum score (55/60/65/70) and minimum reward:risk (1.5/2/2.5) are chosen by expectancy, then applied unchanged to the next unseen test window. Only test windows are reported.
- **Metrics:** trades, wins/losses, win rate (always with the count), profit factor, expectancy (R), average win/loss, total R, net P&L % (compounded at a fixed risk per trade), max drawdown, worst losing streak, breakdowns by side, exit, regime and month. Fewer than 30 trades shows a "too few trades" warning.
- **Kinds are kept separate:** backtests are stored in `backtest_runs` (migration 0004). Prospective results are computed only from live signals that have finished their lifecycle. Paper trading isn't implemented.
- **No accuracy claims:** nothing in the app states an accuracy rate. Results are shown as measured, with their sample size and assumptions.

## Risk, lifecycle and alerts (Milestone 5)

- **Position sizing:** size = (balance × risk%) ÷ per-unit loss, where per-unit loss = |entry − stop| plus fees and slippage on entry and exit. The size is rounded **down** to the exchange lot step, so actual risk never exceeds the limit. The result is checked against the minimum quantity and order value.
- **Futures:** the liquidation estimate uses the simplified isolated-margin formula with the exchange's maintenance-margin rate. It warns if liquidation would come **before** the stop. Leverage changes margin and liquidation distance, not the amount at risk. Funding over the expected holding time is estimated from the current rate.
- **Lifecycle:** signals move through `active → triggered → target_reached`, ending as `target_reached` (TP3), `stopped`, `expired` (no entry before expiry, or a time exit) or `invalidated` (a close beyond the stop before entry).
  - Fills assume the worse edge of the entry zone.
  - Targets are never credited on the entry candle.
  - If a stop and a target are touched in the same candle, the **stop is assumed first** and the event is flagged.
- **Outcome:** each stored signal gets a simulated outcome, labelled as simulated: exits in thirds at TP1/2/3, the rest at stop or time exit, and net R after fees and slippage, excluding funding. Measured performance reporting comes in Milestone 6.
- **Alerts:** in-app only. Alerts are raised for a new LONG/SHORT setup and for every lifecycle event, and the sidebar shows a count of unseen alerts. They're global until accounts exist (Milestone 7). Email and push would be separate, approved work.
- Events are append-only. A signal's evidence, levels and config snapshot stay immutable; only `lifecycle` and `outcome` change.

## Signal engine (Milestone 4)

Strategy **`smc_trend_pullback` v1.0.0**, with `day` (1H, context from 4H), `swing` (4H/1D) and `scalp` (15m/1H) profiles kept as separate versioned configs in `app/signals/strategy.py`.

1. **Data checks:** only closed candles are used. The engine needs at least 200 bars, rejects data more than 2 intervals old, and allows at most 2 missing candles. Any failure → NO TRADE.
2. **Regime:** `volatile` (ATR above 6% of price), `trending_up/down` (ADX ≥ 20, EMA 50 sloping, price on the matching side) or `ranging`. Volatile and ranging → NO TRADE.
3. **Rules:** SMC structure must agree with the regime. There must be an unbroken order block or unfilled fair value gap from the last 60 bars within 1.5 ATR of price. Entry = that zone; stop = zone edge ± 0.25 ATR; targets = resting liquidity (at least 0.5R apart), topped up with 2R/3R/4R.
4. **Evidence:** weighted supporting and conflicting factors: regime, structure, zone, higher-timeframe trend, premium/discount, liquidity sweeps, inducement, RSI, MACD, break volume, candlestick patterns, confirmed formations, and Futures funding.
5. **Reward:risk:** net to TP1 after assumed fees and slippage (spot 0.10% and futures 0.05% fee per side, 0.05% slippage per side) must be ≥ 1.5.
6. **Output:** LONG, SHORT or NO TRADE. The heuristic score is supporting minus conflicting weights (0–100, minimum 60). **It is not a win probability and has not been validated.**
7. **Persistence:** stored with its evidence, assumptions, the full config snapshot and its hash. A unique fingerprint (symbol, market, timeframe, side, strategy version, zone candle) means the same setup is stored once. Rows are **immutable**: only `lifecycle` may change later. The database enforces this, so strategy changes never rewrite old signals.

NO TRADE is an ordinary result. On the 238 synthetic test series, the engine produced 4 signals and 234 NO TRADEs. No accuracy is claimed until Milestone 6 measures outcomes.

## Technical analysis

One library, written twice: `backend/app/analysis` (Python, for the API and the future signal engine) and `assets/js/analysis/ta.js` (so the static site can show readings without a backend). `tests/test_parity.py` runs both on the same candles and fails if any output differs, including the pattern hits.

| Group | Indicators (default settings) |
|---|---|
| Moving averages | SMA, EMA (seeded with the SMA), WMA, VWMA |
| Momentum | RSI 14 (Wilder), MACD 12/26/9, Stochastic 14/3/3, CCI 20, MFI 14 |
| Volatility | ATR 14 (Wilder), Bollinger 20/2 (population σ), Keltner 20/2/ATR 10 |
| Trend | ADX/DMI 14, Supertrend 10/3, Ichimoku 9/26/52, Parabolic SAR 0.02/0.2 |
| Volume | OBV, VWAP (anchored to each UTC day), Volume Profile (24 bins, 70% value area) |
| Levels | Fibonacci retracement (range in view), classic pivots (previous UTC day, or previous bar on 1D) |

- **Warm-up:** values are `null`/`None` until there's enough data (e.g. RSI from bar 15, ADX from bar 28, Ichimoku cloud from bar 78). Nothing is padded or guessed.
- **No look-ahead:** each value uses only bars up to and including its own. A test checks that adding future bars never changes past values. Ichimoku spans are aligned to the bar where the cloud is drawn, and Chikou is the documented exception.
- **Candlestick patterns (27):** Doji, Dragonfly/Gravestone/Long-legged doji, Hammer, Hanging man, Inverted hammer, Shooting star, Bullish/Bearish marubozu, Spinning top, Bullish/Bearish engulfing, Bullish/Bearish harami, Piercing line, Dark cloud cover, Tweezer top/bottom, Morning/Evening star, Three white soldiers, Three black crows, Three inside up/down, Three outside up/down. Thresholds are constants in `patterns.py`. Each hit lists its candles, and every pattern has a hand-built test case.
- **Formations:** fractal swing highs/lows (3 bars each side, so the newest 3 bars are never swings), double top and double bottom (equal within 0.5%, a neckline between them, and "confirmed" only after a close through the neckline).
- Patterns and readings describe past price action. They are context, not predictions, and the UI says so.

## Market data

- **In the browser** (works on GitHub Pages with no backend): `assets/js/providers/binance.js` uses Binance public REST for candles, tickers and mark/index/funding, and WebSockets for live candles and mark price. It reconnects with exponential backoff, treats a feed as stale after 20s of silence, and re-fetches recent candles over REST after every reconnect.
- **Through the backend**: set `api.backendBaseUrl` in `config.js` and the UI uses the TRADE-AI API and its WebSocket streams instead.
- **Region fallback**: Spot uses Binance's public market-data mirror (`data-api.binance.vision`), which isn't region-blocked. If Binance Futures is blocked or unreachable, both the browser and the backend switch Futures to **Hyperliquid perpetuals**. They're labelled as the fallback, with "mid" and "oracle" prices named as such, and prices can differ slightly from Binance USDT-M. The backend re-checks Binance every 10 minutes.
- **Timezone**: all data is kept in UTC. Times are displayed in the timezone chosen under "Display times in" (app sidebar), which is saved in this browser.
- Every view shows the source, the data time and its freshness. If the provider is unreachable, the UI shows an error state, never sample data.
- Spot has no second fallback: if `data-api.binance.vision` itself is down, Spot views show an error state.

## Milestone status

| Milestone | Status |
|---|---|
| 1. Foundation — structure, config, API skeleton, `/health`, DB + migrations, app shell, docs, tests | **Implemented** (see "Verification") |
| 2. Real market data (public Binance Spot/Futures, WebSockets, freshness, reconciliation) | **Implemented**: browser and backend adapters, backend WebSocket hub, Futures region fallback |
| 3. Technical analysis indicators and patterns | **Implemented**: 21 indicators, 27 candlestick patterns, swing points and double tops/bottoms, in Python and JS (parity-tested), API endpoints, chart overlays and readings |
| 4. SMC detections and signal engine | **Implemented**: SMC in Python + JS (parity-tested), signal engine, persistence (migration 0002), scanner, signal API, chart SMC overlay |
| 5. Risk, lifecycle, alerts | **Implemented**: sizing (Python + JS, parity-tested) with exchange specs, lifecycle tracker, events, in-app alerts, migration 0003 |
| Strategy research (v1.1) | **Done — negative result.** No candidate passed the pre-registered rules; holdout untouched. See `research/RESULTS.md`. v1.0.0 is flagged experimental in the app |
| 6. Backtesting and performance | **Implemented**: backtester (no look-ahead, 1m collision resolver, costs, funding, latency), splits, walk-forward, metrics, storage, CLI, API, History page |
| 7. Accounts and server-side 3-signal trial | Not started |
| 8. Billing | Out of scope until explicitly requested — no checkout, no payment data |

Pages using real market data: dashboard, market overview, watchlist and advanced chart. Pages that still need backend work: signals, scanner, pattern & SMC, futures intelligence, signal history, alerts, account, billing. They show "not connected" / "not available yet" states and never substitute sample data unless demo mode is switched on.

Trial length and renewal terms are unset (`pricing.trialDurationDays`, `pricing.renewalTerms`) and display "to be confirmed".

## Verification

- Backend tests: run by GitHub Actions (`.github/workflows/ci.yml`) on every push, against SQLite and Postgres. Binance is mocked in tests (GitHub's runners are in a region Binance blocks).
- Live smoke test (CI, informational): runs the real API against real public data and checks the REST endpoints and both WebSocket streams. GitHub's runners are in the US, so this also exercises the Futures fallback.
- Frontend: `node --check` on all JS in CI.

## Updating the frontend
After changing CSS/JS, bump the `?v=N` on asset links in `index.html` and `app.html` so browsers fetch the new files.

## Risk disclosure
Cryptocurrency trading, especially with leverage, carries a high risk of loss. TRADE-AI provides analysis for information only and is not financial advice.
