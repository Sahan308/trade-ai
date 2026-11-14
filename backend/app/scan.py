"""Scanner: evaluate the configured markets and store the results.

    python -m app.scan                # one pass
    python -m app.scan --loop 300     # every 300 seconds
"""
import argparse
import logging
import time
from datetime import datetime, timezone

from .config import get_settings
from .db import get_engine, get_session
from .providers.base import MarketType, ProviderError
from .signals.engine import evaluate
from .signals.store import save
from .signals.tracker import alert_for_new_signal, track_open
from .signals.strategy import PROFILES

log = logging.getLogger("tradeai.scan")


def _series(provider, market, symbol, interval, limit):
    s = provider.candles(market, symbol, interval, limit)
    cs = s.candles
    return s, {"t": [x.open_time.timestamp() * 1000 for x in cs], "o": [x.open for x in cs], "h": [x.high for x in cs],
               "l": [x.low for x in cs], "c": [x.close for x in cs], "v": [x.volume for x in cs]}


def evaluate_symbol(provider, symbol: str, market: str, profile: str = "day", now: datetime | None = None) -> dict:
    cfg = PROFILES[profile]
    now = now or datetime.now(timezone.utc)
    mkt = MarketType(market)
    s, series = _series(provider, mkt, symbol, cfg.timeframe, 300)
    _, htf = _series(provider, mkt, symbol, cfg.htf, 200)
    funding = None
    if mkt == MarketType.futures:
        try:
            funding = provider.funding(symbol).funding_rate
        except ProviderError:
            funding = None
    return evaluate(series, htf, symbol=symbol.upper(), market=market, source=s.source, cfg=cfg, now=now,
                    gaps=s.gaps, funding_rate=funding)


def scan_once(provider, profile: str = "day") -> list[dict]:
    out = []
    for entry in get_settings().markets:
        sym, _, mkt = entry.partition(":")
        try:
            res = evaluate_symbol(provider, sym, mkt or "spot", profile)
        except ProviderError as exc:
            log.warning("scan %s %s skipped: %s", sym, mkt, exc.message)
            continue
        session = next(get_session())
        try:
            row, created = save(session, res)
            if created and row.side in ("LONG", "SHORT"):
                alert_for_new_signal(session, row)
                session.commit()
        finally:
            session.close()
        log.info("scan %s %s → %s%s", sym, mkt, res["side"], "" if created else " (already stored)")
        out.append({"id": row.id, "symbol": sym, "market": mkt, "side": res["side"], "created": created})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loop", type=int, default=0, help="seconds between passes (0 = run once)")
    ap.add_argument("--profile", default="day", choices=sorted(PROFILES))
    args = ap.parse_args()
    logging.basicConfig(level=get_settings().log_level.upper(), format="%(asctime)s %(levelname)s %(message)s")
    from .main import default_provider
    provider = default_provider(get_settings())
    get_engine()
    while True:
        for r in scan_once(provider, args.profile):
            print(r)
        session = next(get_session())
        try:
            print({"lifecycle_events": track_open(session, provider)})
        finally:
            session.close()
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
