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
    # Symbols listed by /api/markets, as SYMBOL:market pairs
    markets: Annotated[list[str], NoDecode] = ["BTCUSDT:spot", "ETHUSDT:spot", "SOLUSDT:futures", "BNBUSDT:spot", "XRPUSDT:futures"]
    # Inbound API rate limit per client IP
    rate_limit_per_minute: int = 120

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
