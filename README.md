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
      app/api/analysis.py       /api/analysis and /api/patterns
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
| 4. SMC detections and signal engine | Not started |
| 5. Risk, lifecycle, alerts | Frontend position-size calculator only |
| 6. Backtesting and performance | Not started |
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
