"""Settings loaded from environment variables (prefix TRADEAI_) or a .env file."""
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADEAI_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./tradeai.db"
    # NoDecode: accept a plain comma-separated string instead of requiring JSON
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:8080"]
    log_level: str = "INFO"

    # Market data (public, key-less)
    binance_spot_base: str = "https://data-api.binance.vision"
    binance_futures_base: str = "https://fapi.binance.com"
    # Futures fallback when Binance Futures is region-blocked/unreachable (empty string disables)
    futures_fallback_base: str = "https://api.hyperliquid.xyz"
    # Symbols listed by /api/markets, as SYMBOL:market pairs
    markets: Annotated[list[str], NoDecode] = ["BTCUSDT:spot", "ETHUSDT:spot", "SOLUSDT:futures", "BNBUSDT:spot", "XRPUSDT:futures"]
    # Inbound API rate limit per client IP
    rate_limit_per_minute: int = 120
    # Stricter limit for sign-in / sign-up / password endpoints (per client IP)
    auth_rate_limit_per_minute: int = 10
    # Shared limiter store for multi-process / multi-server deployments, e.g. redis://localhost:6379/0
    redis_url: str | None = None
    # Concurrent WebSocket connections per client IP (per process)
    ws_max_per_ip: int = 10

    # Accounts (Milestone 7). Secret signs session tokens; required in production.
    auth_secret: str = "dev-only-insecure-secret-change-me"
    token_ttl_hours: int = 24 * 14
    trial_signals: int = 3  # legacy (signal-unlock trial, replaced by trial_days)
    trial_days: int = 7
    # Billing (Lemon Squeezy). Empty secret = webhook disabled.
    lemonsqueezy_webhook_secret: str = ""
    # Telegram channel alerts (optional). Bot token from @BotFather; chat id like -100… or @channelname.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    public_site_url: str = "https://sahan308.github.io/trade-ai/app.html"
    # Google sign-in (OAuth Client ID from Google Cloud; public, not a secret). Empty = disabled.
    google_client_id: str = ""
    # Web push (VAPID). Generated on the server; empty = browser push disabled.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:alerts@tradeai.invalid"
    # Outgoing email (password reset) via any SMTP provider, e.g. Brevo. Empty host = disabled.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""
    # Comma-separated emails allowed to view usage stats
    admin_emails: Annotated[list[str], NoDecode] = []

    @field_validator("database_url", mode="before")
    @classmethod
    def normalise_db_url(cls, v):
        """Hosted Postgres providers hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver."""
        if isinstance(v, str):
            for prefix in ("postgres://", "postgresql://"):
                if v.startswith(prefix):
                    return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("cors_origins", "markets", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("cors_origins")
    @classmethod
    def no_wildcard_in_prod(cls, v, info):
        if info.data.get("env") == "production" and "*" in v:
            raise ValueError("Wildcard CORS origin is not allowed in production")
        return v


    @field_validator("admin_emails", mode="before")
    @classmethod
    def split_admin(cls, v):
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return [x.lower() for x in (v or [])]

    @field_validator("auth_secret")
    @classmethod
    def strong_secret_in_prod(cls, v, info):
        if info.data.get("env") == "production" and (len(v) < 32 or v.startswith("dev-only")):
            raise ValueError("TRADEAI_AUTH_SECRET must be set to a random value of at least 32 characters in production")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
