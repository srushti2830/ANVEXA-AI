from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_EMBEDDING_MODELS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "sentence-transformers/paraphrase-MiniLM-L3-v2": 384,
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
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=1, le=2000)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
