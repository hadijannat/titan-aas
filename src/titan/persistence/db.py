"""Async database engine and session factory.

Provides PostgreSQL async connectivity using SQLAlchemy 2.0 asyncio
extension with asyncpg driver.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from titan.config import settings

# Module-level engine (initialized lazily)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine.

    The engine is created lazily on first access using connection pool
    settings appropriate for industrial workloads.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=1800,  # Recycle connections after 30 minutes
            pool_pre_ping=True,  # Verify connection health
            echo=settings.env == "dev",  # Log SQL in dev
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for FastAPI dependency injection.

    Usage:
        @router.get("/")
        async def handler(session: AsyncSession = Depends(get_session)):
            ...
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        await session.close()


@asynccontextmanager
async def session_context() -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around a series of operations.

    Usage:
        async with session_context() as session:
            result = await session.execute(...)
            await session.commit()
    """
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Initialize database (create tables if not exists).

    For production, use Alembic migrations instead.
    """
    from titan.persistence.tables import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def health_check() -> bool:
    """Check database connectivity."""
    try:
        async with session_context() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
