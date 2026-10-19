"""Application composition. Keep domain behavior in its owning package."""

from fastapi import FastAPI

from src import logging as app_logging
from src.config import Settings
from src.health.router import router as health_router

VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    app_logging.configure_logging(config.log_level)
    app = FastAPI(
        title="Weft Engine",
        version=VERSION,
        description="Weft backend engine. Matching features are not implemented yet.",
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.docs_enabled else None,
    )
    app.include_router(health_router)
    return app
