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
      services/                 marketData.js, signals.js, health.js — the only code that calls the network
      fixtures/demo.js          Isolated, labelled sample data (demo mode only)
    backend/                    FastAPI service (Milestone 1)
      app/main.py               App factory: CORS allowlist, request IDs, security headers, error handlers
      app/config.py             Settings from TRADEAI_* environment variables / .env
      app/db.py, app/models.py  SQLAlchemy 2.0 engine/session + models (audit_logs)
      app/api/health.py         GET /health
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

Secrets belong in environment variables or `.env` (git-ignored), never in `assets/js/config.js`.

## API (implemented endpoints only)

`GET /health` → `200` when healthy, `503` when the database is unreachable.

```json
{ "status": "ok", "version": "0.1.0", "environment": "development",
  "time_utc": "2026-11-14T10:00:00Z", "components": { "database": { "status": "ok", "error": null } } }
```

Errors use one envelope: `{"error": {"code": "not_found", "message": "...", "request_id": "..."}}`. Every response carries `X-Request-ID`. Internal error details are logged, never returned.

No other endpoints exist yet.

## Milestone status

| Milestone | Status |
|---|---|
| 1. Foundation — structure, config, API skeleton, `/health`, DB + migrations, app shell, docs, tests | **Implemented** (see "Verification") |
| 2. Real market data (public Binance Spot/Futures, WebSockets, freshness, reconciliation) | Not started |
| 3. Technical analysis indicators and patterns | Not started |
| 4. SMC detections and signal engine | Not started |
| 5. Risk, lifecycle, alerts | Frontend position-size calculator only |
| 6. Backtesting and performance | Not started |
| 7. Accounts and server-side 3-signal trial | Not started |
| 8. Billing | Out of scope until explicitly requested — no checkout, no payment data |

Frontend pages that still need backend work: market overview, watchlist, signals, advanced chart, scanner, pattern & SMC, futures intelligence, signal history, alerts, account, billing. They show "not connected" / "not available yet" states and never substitute sample data unless demo mode is switched on.

Trial length and renewal terms are unset (`pricing.trialDurationDays`, `pricing.renewalTerms`) and display "to be confirmed".

## Verification

- Backend tests: run by GitHub Actions (`.github/workflows/ci.yml`) on every push, against SQLite and Postgres.
- Frontend: `node --check` on all JS in CI.

## Updating the frontend
After changing CSS/JS, bump the `?v=N` on asset links in `index.html` and `app.html` so browsers fetch the new files.

## Risk disclosure
Cryptocurrency trading, especially with leverage, carries a high risk of loss. TRADE-AI provides analysis for information only and is not financial advice.
