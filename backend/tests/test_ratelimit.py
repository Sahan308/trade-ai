import asyncio

import fakeredis
import pytest

from app.ratelimit import MemoryRateLimiter, RedisRateLimiter


def run(coro):
    return asyncio.run(coro)


def test_memory_limiter():
    lim = MemoryRateLimiter(2)
    assert [run(lim.allow("ip"))[0] for _ in range(3)] == [True, True, False]
    assert run(lim.allow("other"))[0] is True


def test_redis_limiter_is_shared_between_processes():
    async def go():
        server = fakeredis.FakeServer()
        a = RedisRateLimiter(fakeredis.FakeAsyncRedis(server=server), 3)   # "process" A
        b = RedisRateLimiter(fakeredis.FakeAsyncRedis(server=server), 3)   # "process" B
        results = [(await a.allow("1.2.3.4"))[0], (await b.allow("1.2.3.4"))[0], (await a.allow("1.2.3.4"))[0]]
        denied, retry = await b.allow("1.2.3.4")
        other = (await b.allow("5.6.7.8"))[0]
        return results, denied, retry, other
    results, denied, retry, other = run(go())
    assert results == [True, True, True] and denied is False and 1 <= retry <= 60 and other is True


def test_redis_limiter_fails_open():
    class Broken:
        def pipeline(self):
            raise ConnectionError("redis down")
    assert run(RedisRateLimiter(Broken(), 1).allow("ip")) == (True, 0)


def test_app_uses_redis_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEAI_DATABASE_URL", f"sqlite:///{tmp_path / 'r.db'}")
    from app.ratelimit import build_limiter
    lim = build_limiter(10, "redis://localhost:6399/0")
    assert isinstance(lim, RedisRateLimiter) and lim.shared
    assert isinstance(build_limiter(10, None), MemoryRateLimiter)
