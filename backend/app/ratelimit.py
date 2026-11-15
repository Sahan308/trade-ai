"""Rate limiting for /api/* and WebSocket connection attempts.

* No TRADEAI_REDIS_URL  → in-memory token bucket (correct for a single process).
* TRADEAI_REDIS_URL set → shared fixed-window counter in Redis, correct across processes/servers.
If Redis is unreachable the limiter fails open (requests allowed) and logs a warning, so a Redis
outage can't take the API down."""
import asyncio
import logging
import threading
import time
import uuid

from fastapi import Request

from .errors import error_response

log = logging.getLogger("tradeai.ratelimit")


class MemoryRateLimiter:
    shared = False

    def __init__(self, per_minute: int):
        self.capacity = max(1, per_minute)
        self.rate = self.capacity / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    async def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True, 0
            self._buckets[key] = (tokens, now)
            return False, int((1 - tokens) / self.rate) + 1


class RedisRateLimiter:
    shared = True

    def __init__(self, redis, per_minute: int, prefix: str = "tradeai:rl"):
        self.redis, self.limit, self.prefix = redis, max(1, per_minute), prefix

    async def allow(self, key: str) -> tuple[bool, int]:
        now = time.time()
        window = int(now // 60)
        rkey = f"{self.prefix}:{key}:{window}"
        try:
            pipe = self.redis.pipeline()
            pipe.incr(rkey)
            pipe.expire(rkey, 61)
            count, _ = await asyncio.wait_for(pipe.execute(), timeout=0.5)
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis rate limiter unavailable (%s); allowing request", exc.__class__.__name__)
            return True, 0
        if int(count) <= self.limit:
            return True, 0
        return False, max(1, 60 - int(now % 60))


def build_limiter(per_minute: int, redis_url: str | None):
    if not redis_url:
        return MemoryRateLimiter(per_minute)
    import redis.asyncio as aioredis

    return RedisRateLimiter(aioredis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5), per_minute)


AUTH_PATHS = ("/api/auth/login", "/api/auth/register", "/api/auth/password", "/api/auth/delete")


def install_rate_limit(app, limiter, auth_limiter=None) -> None:
    app.state.rate_limiter = limiter
    auth_limiter = auth_limiter or MemoryRateLimiter(10)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            ip = request.client.host if request.client else "unknown"
            ok, retry = await limiter.allow(ip)
            if ok and request.method == "POST" and request.url.path in AUTH_PATHS:
                ok, retry = await auth_limiter.allow(f"auth:{ip}")
            if not ok:
                if not getattr(request.state, "request_id", None):
                    request.state.request_id = uuid.uuid4().hex
                resp = error_response(request, 429, "rate_limited", "Too many requests")
                resp.headers["Retry-After"] = str(retry)
                return resp
        return await call_next(request)
