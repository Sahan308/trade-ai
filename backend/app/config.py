"""Settings loaded from environment variables (prefix TRADEAI_) or a .env file."""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADEAI_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./tradeai.db"
    cors_origins: list[str] = ["http://localhost:8080"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
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
