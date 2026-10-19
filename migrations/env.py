"""Alembic entry point; migration discovery is restricted to weft_engine."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.matching.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def database_url() -> str:
    value = os.environ.get("WEFT_MATCHING_DATABASE_URL")
    if not value:
        raise RuntimeError("WEFT_MATCHING_DATABASE_URL is required for Alembic")
    return value


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="weft_engine",
        include_name=include_engine_schema,
    )
    with context.begin_transaction():
        context.execute("CREATE SCHEMA IF NOT EXISTS weft_engine")
        context.run_migrations()


def include_engine_schema(name: str | None, type_: str, _parent_names: dict[str, str]) -> bool:
    return type_ != "schema" or name == "weft_engine"


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="weft_engine",
        include_name=include_engine_schema,
    )
    with context.begin_transaction():
        connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS weft_engine")
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
