# TRADE-AI — website (static front end)

Explainable crypto market analysis UI: landing page + signed-in app shell.
Analysis and decision support only. It never places trades or asks for exchange permissions.

## Run locally
No build step and no dependencies.

    cd trade-ai
    python3 -m http.server 8080
    # open http://localhost:8080        (landing)
    #      http://localhost:8080/app.html  (app)
    #      http://localhost:8080/app.html?demo=1  (app with sample preview on)

You can also double-click `index.html`, because the code uses classic scripts, not ES modules.

## Structure
    index.html, app.html          pages
    assets/css/base.css           design tokens + shared components (buttons, badges, cards, modal, signal card)
    assets/css/landing.css        landing page
    assets/css/app.css            app shell, tables, states, forms
    assets/js/config.js           public config: pricing, trial terms, API URLs (no secrets)
    assets/js/core.js             icon set, formatting, scroll reveal, modal, toast
    assets/js/components.js       signal card, signal detail, candlestick chart
    assets/js/services/*.js       market data + signals services (the only place data is fetched)
    assets/js/fixtures/demo.js    ISOLATED sample data, used only when demo mode is on, always labelled
    assets/js/landing.js, app.js  page logic (hash router for the app)

## Data honesty rules built in
- With no API configured, the app shows "not connected" states. It never shows invented numbers.
- Sample mode (the toggle or `?demo=1`) puts a banner, badges and "Sample price" headers on the screen.
- The setup score is always labelled a heuristic, never a win probability.
- Measured performance and unvalidated estimates are kept in separate, visually distinct panels.

## Needs backend / integration
| Area | Status |
|---|---|
| Market data (watchlist, overview, chart) | UI done; set `api.marketDataBaseUrl` (contract in services/marketData.js) |
| Signals + trial usage | UI done; set `api.signalsBaseUrl` (contract in services/signals.js). No signal engine in the frontend. |
| Signal history / performance | Layout only; needs a backend that tracks outcomes |
| Scanner, Pattern & SMC, Futures intelligence, Alerts, Account | Placeholder "not available yet" states |
| Sign in / auth | Not implemented (links go to the app preview) |
| Billing / checkout | Not implemented; `pricing.checkoutEnabled: false` |
| Trial length, renewal terms | `null` in config, shown as "to be confirmed" |
| Footer legal pages | Placeholder links in `config.links` |

The Risk manager (position size calculator) works fully offline from the numbers you type in.

## Accessibility & motion
Keyboard-operable nav, accordion, tabs and modal (with a focus trap and Escape to close). Visible focus rings. Direction is shown with text + icon, not colour alone. Scroll reveals use IntersectionObserver. With `prefers-reduced-motion`, content shows immediately and animations are off.

No automated tests are included.

## Updating
After changing CSS/JS, bump the `?v=N` on asset links in index.html and app.html so browsers fetch the new files.
