"""Download public historical candles for strategy research (not committed to the repo).

    python scripts/fetch_history.py --out ../research-data --days 730 BTCUSDT ETHUSDT ...
Writes <out>/<SYMBOL>_<TF>.json.gz with {"t","o","h","l","c","v"} arrays (spot, UTC open times in ms).
"""
import argparse
import gzip
import json
import os
from datetime import datetime, timezone

from app.providers.base import INTERVAL_MS, MarketType
from app.providers.binance import BinanceProvider


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--tfs", default="1H,4H")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    p = BinanceProvider("https://data-api.binance.vision", "https://fapi.binance.com")
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    for sym in a.symbols:
        for tf in a.tfs.split(","):
            step = INTERVAL_MS[tf]
            end = now // step * step
            s = p.history(MarketType.spot, sym, tf, end - a.days * 86_400_000, end)
            data = {"symbol": sym, "tf": tf, "source": s.source, "gaps": s.gaps, "dropped": s.dropped,
                    "t": [int(c.open_time.timestamp() * 1000) for c in s.candles], "o": [c.open for c in s.candles],
                    "h": [c.high for c in s.candles], "l": [c.low for c in s.candles], "c": [c.close for c in s.candles],
                    "v": [c.volume for c in s.candles]}
            with gzip.open(os.path.join(a.out, f"{sym}_{tf}.json.gz"), "wt") as f:
                json.dump(data, f)
            print(sym, tf, len(data["t"]), "candles, gaps", s.gaps)


if __name__ == "__main__":
    main()
