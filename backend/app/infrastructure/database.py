from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger("escroweye.database")


class Base(DeclarativeBase):
    pass


_engine: Any = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = settings.database_url()
        logger.info("Creating async engine", extra={"url": db_url})
        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.close()

    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager for database sessions.

    Usage:
        async with get_session() as session:
            ...  # auto-commits on success, rolls back on exception
    """
    maker = get_session_maker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session.

    Usage in routes:
        async def my_route(session: AsyncSession = Depends(get_db)):
            ...
    """
    maker = get_session_maker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def reset_engine() -> None:
    global _engine, _async_session_maker  # noqa: PLW0603
    _engine = None
    _async_session_maker = None


async def create_tables() -> None:
    from app.infrastructure.models import Base as ModelsBase

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
    logger.info("Database tables created/verified")


async def drop_tables() -> None:
    from app.infrastructure.models import Base as ModelsBase

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.drop_all)
    logger.info("Database tables dropped")


async def close_engine() -> None:
    global _engine, _async_session_maker
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None
        logger.info("Database engine disposed")
