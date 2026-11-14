import json

import httpx
import pytest

from app.providers.base import MarketType, ProviderError
from app.providers.binance import BinanceProvider
from app.providers.fallback import FallbackProvider
from app.providers.hyperliquid import HyperliquidProvider, to_coin
from tests.test_markets import FakeBinance

T0 = 1_794_643_200_000
H = 3_600_000


def hl_handler(calls):
    def handle(request: httpx.Request):
        calls.append(request)
        body = json.loads(request.content)
        if body["type"] == "metaAndAssetCtxs":
            return httpx.Response(200, json=[{"universe": [{"name": "SOL"}, {"name": "XRP"}]},
                                             [{"funding": "0.0000125", "prevDayPx": "80", "dayNtlVlm": "354565934", "oraclePx": "75.86", "markPx": "75.82", "midPx": "75.83"},
                                              {"funding": "0.00001", "prevDayPx": "1", "dayNtlVlm": "1000", "oraclePx": "0.99", "markPx": "0.98", "midPx": "0.985"}]])
        if body["type"] == "candleSnapshot":
            return httpx.Response(200, json=[{"t": T0 + i * H, "T": T0 + (i + 1) * H - 1, "o": "75", "h": "76", "l": "74", "c": "75.5", "v": "100"} for i in range(3)])
        return httpx.Response(400, json={})
    return handle


@pytest.fixture()
def setup():
    fake = FakeBinance()
    hl_calls = []
    primary = BinanceProvider("https://spot.test", "https://fut.test", client=httpx.Client(transport=httpx.MockTransport(fake)))
    hl = HyperliquidProvider("https://hl.test", client=httpx.Client(transport=httpx.MockTransport(hl_handler(hl_calls))))
    return fake, hl_calls, FallbackProvider(primary, hl)


def test_futures_switch_to_fallback_on_region_block(setup):
    fake, hl_calls, p = setup
    fake.status = 451
    f = p.funding("SOLUSDT")
    assert f.source == "Hyperliquid perpetuals (fallback)" and f.index_label == "Oracle price"
    assert f.mark_price == 75.82 and f.index_price == 75.86
    assert p.using_fallback
    n = len(fake.calls)
    t = p.ticker(MarketType.futures, "XRPUSDT")          # stays on fallback without re-hitting the primary
    assert t.price_label == "Mid price" and len(fake.calls) == n
    s = p.candles(MarketType.futures, "SOLUSDT", "1H", 3)
    assert len(s.candles) == 3 and s.source.startswith("Hyperliquid")
    assert p.kline_stream(MarketType.futures, "SOLUSDT", "1H").url == "wss://api.hyperliquid.xyz/ws"


def test_spot_never_uses_fallback(setup):
    fake, hl_calls, p = setup
    fake.status = 451
    with pytest.raises(ProviderError) as e:
        p.ticker(MarketType.spot, "BTCUSDT")
    assert e.value.kind == "region_blocked" and not hl_calls


def test_primary_used_when_healthy(setup):
    fake, hl_calls, p = setup
    assert p.funding("SOLUSDT").source == "Binance USDT-M Futures" and not hl_calls and not p.using_fallback


def test_rechecks_primary_after_window(setup):
    fake, hl_calls, p = setup
    p.recheck_seconds = 0
    fake.status = 451
    p.funding("SOLUSDT")
    fake.status = None
    assert p.funding("SOLUSDT").source == "Binance USDT-M Futures" and not p.using_fallback


def test_bad_request_does_not_trigger_fallback(setup):
    fake, hl_calls, p = setup
    fake.status = 400
    with pytest.raises(ProviderError):
        p.funding("SOLUSDT")
    assert not hl_calls and not p.using_fallback


def test_coin_mapping():
    assert to_coin("SOL/USDT") == "SOL" and to_coin("btcusdt") == "BTC"
    with pytest.raises(ProviderError):
        to_coin("!")
