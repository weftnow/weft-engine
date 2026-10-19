"""Application configuration; domain settings belong in their owning packages."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import model_validator
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
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    docs_enabled: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @model_validator(mode="after")
    def protect_production_docs(self) -> Settings:
        if self.environment is Environment.PRODUCTION and self.docs_enabled:
            raise ValueError("Set WEFT_DOCS_ENABLED=false in production")
        return self
