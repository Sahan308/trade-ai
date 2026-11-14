"""Simple in-memory token bucket per client IP for /api/* routes.
Single-process only; use a shared store (e.g. Redis) when running several workers."""
import threading
import time

from fastapi import Request

from .errors import error_response


class RateLimiter:
    def __init__(self, per_minute: int):
        self.capacity = max(1, per_minute)
        self.rate = self.capacity / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True, 0
            self._buckets[key] = (tokens, now)
            return False, int((1 - tokens) / self.rate) + 1


def install_rate_limit(app, per_minute: int) -> None:
    limiter = RateLimiter(per_minute)
    app.state.rate_limiter = limiter

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            ip = request.client.host if request.client else "unknown"
            ok, retry = limiter.allow(ip)
            if not ok:
                if not getattr(request.state, "request_id", None):
                    import uuid
                    request.state.request_id = uuid.uuid4().hex
                resp = error_response(request, 429, "rate_limited", "Too many requests")
                resp.headers["Retry-After"] = str(retry)
                return resp
        return await call_next(request)
