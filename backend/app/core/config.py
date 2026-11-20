from functools import lru_cache
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_EMBEDDING_MODELS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "sentence-transformers/paraphrase-MiniLM-L3-v2": 384,
    "sentence-transformers/all-mpnet-base-v2": 768,
}


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
    dev_database_mode: bool = False
    dev_sqlite_url: str = "sqlite+pysqlite:///./storage/anvexa-dev.sqlite3"
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=1, le=2000)

    # Authentication & Security
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    auth_rate_limit_max_attempts: int = Field(default=5, ge=1)
    auth_rate_limit_lockout_seconds: int = Field(default=300, ge=1)

    # Document Management
    document_storage_path: str = "./storage/documents"
    max_upload_size_bytes: int = Field(default=52_428_800, ge=1)  # 50 MB
    allowed_file_extensions: list[str] = Field(default=[".pdf", ".docx"])
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    gemini_max_retries: int = Field(default=2, ge=0, le=5)
    crossref_api_url: str = "https://api.crossref.org"
    openalex_api_url: str = "https://api.openalex.org"
    source_retrieval_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    source_retrieval_max_retries: int = Field(default=2, ge=0, le=5)

    @property
    def active_database_url(self) -> str | None:
        if self.dev_database_mode:
            return self.dev_sqlite_url
        return (
            self.database_url.get_secret_value()
            if self.database_url is not None
            else None
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            value_stripped = value.strip()
            if value_stripped.startswith("["):
                try:
                    parsed = json.loads(value_stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except Exception:
                    pass
            return [
                origin.strip()
                for origin in value_stripped.split(",")
                if origin.strip()
            ]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value]
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    @model_validator(mode="after")
    def validate_embedding_configuration(self) -> Settings:
        expected_dimension = SUPPORTED_EMBEDDING_MODELS.get(self.embedding_model)
        if expected_dimension is None:
            raise ValueError(
                f"Unsupported embedding model: {self.embedding_model}"
            )
        if self.embedding_dimension != expected_dimension:
            raise ValueError(
                f"{self.embedding_model} requires vector dimension "
                f"{expected_dimension}."
            )
        return self

    @model_validator(mode="after")
    def validate_development_database_configuration(self) -> Settings:
        if not self.dev_database_mode:
            return self
        if self.environment != "development":
            raise ValueError(
                "ANVEXA_DEV_DATABASE_MODE is allowed only when "
                "ANVEXA_ENVIRONMENT=development."
            )
        if not self.dev_sqlite_url.startswith(("sqlite:", "sqlite+")):
            raise ValueError(
                "ANVEXA_DEV_SQLITE_URL must use a SQLite SQLAlchemy URL."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
