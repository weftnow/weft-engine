"""Application composition. Keep domain behavior in its owning package."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src import logging as app_logging
from src.config import Settings
from src.health.router import router as health_router
from src.matching.console import ConsoleAdapter
from src.matching.router import router as matching_router
from src.matching.storage import session_factory

VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    app_logging.configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        engine = getattr(application.state, "console_engine", None)
        if isinstance(engine, AsyncEngine):
            await engine.dispose()
        sessions = getattr(application.state, "matching_sessions", None)
        if sessions is not None:
            await sessions.kw["bind"].dispose()

    app = FastAPI(
        title="Weft Engine",
        version=VERSION,
        description="Weft backend engine, including live matching service operations.",
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.docs_enabled else None,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(matching_router)
    app.state.settings = config
    if config.matching_database_url:
        app.state.matching_sessions = session_factory(
            config.matching_database_url.get_secret_value()
        )
    if config.console_database_url:
        app.state.console_engine = create_async_engine(
            config.console_database_url.get_secret_value(),
            pool_pre_ping=True,
            hide_parameters=True,
            isolation_level="REPEATABLE READ",
        )
        app.state.console_adapter = ConsoleAdapter(app.state.console_engine)

    return app
