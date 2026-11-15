"""FastAPI application factory. Run: uvicorn app.main:app --reload"""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.accounts import router as accounts_router
from .api.alerts import router as alerts_router
from .api.billing import router as billing_router
from .api.stats import router as stats_router
from .api.analysis import router as analysis_router
from .api.health import router as health_router
from .api.markets import router as markets_router
from .api.performance import router as performance_router
from .api.risk import router as risk_router
from .api.signals import router as signals_router
from .config import get_settings
from .errors import install_error_handlers
from .api.streams import router as streams_router
from .providers.binance import BinanceProvider
from .providers.fallback import FallbackProvider
from .providers.hyperliquid import HyperliquidProvider
from .ratelimit import MemoryRateLimiter, build_limiter, install_rate_limit
from .streams import StreamHub


def default_provider(settings):
    primary = BinanceProvider(settings.binance_spot_base, settings.binance_futures_base)
    fb = HyperliquidProvider(settings.futures_fallback_base) if settings.futures_fallback_base else None
    return FallbackProvider(primary, fb)


def create_app(provider=None, hub: StreamHub | None = None, limiter=None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.hub.close()
        close = getattr(app.state.provider, "close", None)
        if close:
            close()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(
        title="TRADE-AI API",
        version=__version__,
        description="Market analysis and decision support. Read-only: never places trades or requests exchange keys.",
        docs_url=None if settings.env == "production" else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.provider = provider or default_provider(settings)
    app.state.hub = hub or StreamHub()
    app.state.ws_counts = {}


    @app.middleware("http")
    async def request_id_and_headers(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if settings.env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    install_rate_limit(app, limiter or build_limiter(settings.rate_limit_per_minute, settings.redis_url), MemoryRateLimiter(settings.auth_rate_limit_per_minute))
    # CORS is added last so it wraps everything (including 429 responses from the rate limiter).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],  # POST only for accounts / unlocks
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(markets_router)
    app.include_router(analysis_router)
    app.include_router(alerts_router)
    @app.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Cache-Control", "no-store") if request.url.path.startswith("/api/auth") else None
        if settings.env == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    app.include_router(accounts_router)
    app.include_router(billing_router)
    app.include_router(stats_router)
    app.include_router(signals_router)
    app.include_router(risk_router)
    app.include_router(performance_router)
    app.include_router(streams_router)
    return app


app = create_app()
