"""Application configuration; domain settings belong in their owning packages."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEFT_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    docs_enabled: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    matching_database_url: SecretStr | None = None
    console_database_url: SecretStr | None = None
    matching_service_tokens: dict[str, list[str]] = Field(default_factory=dict)
    openai_api_key: SecretStr | None = None
    matching_embedding_model: str = "text-embedding-3-large"
    matching_evaluation_model: str = "gpt-6.1-sol"
    matching_prompt_version: str = "f06-rubric-v1"
    matching_policy_version: str = "f06-policy-v1"
    matching_max_spend_usd: float = 0.0
    matching_input_cost_per_million_usd: float = 0.0
    matching_output_cost_per_million_usd: float = 0.0
    matching_worker_id: str = "weft-matching-worker"
    matching_provider_concurrency: int = Field(default=2, ge=1, le=8)
    matching_embedding_cost_per_million_usd: float = 0.0
    matching_automatic_enabled: bool = False
    matching_change_quiet_seconds: int = Field(default=30, ge=0)
    matching_change_max_wait_seconds: int = Field(default=300, ge=0)
    matching_change_retry_limit: int = Field(default=3, ge=0, le=10)
    matching_change_poll_limit: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def protect_production_docs(self) -> Settings:
        if self.environment is Environment.PRODUCTION and self.docs_enabled:
            raise ValueError("Set WEFT_DOCS_ENABLED=false in production")
        return self
