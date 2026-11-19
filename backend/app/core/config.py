from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANVEXA_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ANVEXA AI API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = Field(default="/api/v1", pattern=r"^/")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
