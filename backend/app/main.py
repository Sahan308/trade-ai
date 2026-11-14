"""FastAPI application factory. Run: uvicorn app.main:app --reload"""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.health import router as health_router
from .api.markets import router as markets_router
from .config import get_settings
from .errors import install_error_handlers
from .providers.binance import BinanceProvider
from .ratelimit import install_rate_limit


def create_app(provider=None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
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
    app.state.provider = provider or BinanceProvider(settings.binance_spot_base, settings.binance_futures_base)


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

    install_rate_limit(app, settings.rate_limit_per_minute)
    # CORS is added last so it wraps everything (including 429 responses from the rate limiter).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],          # read-only API for now
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(markets_router)
    return app


app = create_app()
