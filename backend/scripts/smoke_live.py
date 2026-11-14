"""Live smoke test against REAL public market data (not part of the unit tests).
Starts nothing itself: expects the API at http://127.0.0.1:8000. Prints what it got."""
import asyncio
import json
import sys

import httpx
import websockets

API = "http://127.0.0.1:8000"


async def first_event(path, want, timeout=45):
    async with websockets.connect(f"ws://127.0.0.1:8000{path}") as ws:
        async def loop():
            while True:
                m = json.loads(await ws.recv())
                if m["type"] == want:
                    return m
        return await asyncio.wait_for(loop(), timeout)


async def main():
    ok = True
    with httpx.Client(base_url=API, timeout=20) as c:
        for url in ["/api/markets/BTCUSDT/ticker?market=spot", "/api/markets/SOLUSDT/ticker?market=futures",
                    "/api/futures/SOLUSDT/funding", "/api/markets/BTCUSDT/candles?market=spot&interval=1H&limit=5"]:
            r = c.get(url)
            body = r.json()
            summary = {k: body.get(k) for k in ("source", "last_price", "price_label", "mark_price", "index_price", "index_label", "gaps")} if r.is_success else body
            print(r.status_code, url, json.dumps(summary))
            ok &= r.is_success
    for path, want in [("/ws/chart/BTCUSDT/1m?market=spot", "candle"), ("/ws/market/SOLUSDT", "funding")]:
        try:
            m = await first_event(path, want)
            print("WS ok", path, json.dumps(m)[:200])
        except Exception as e:  # noqa: BLE001
            print("WS FAILED", path, repr(e))
            ok = False
    sys.exit(0 if ok else 1)


asyncio.run(main())
