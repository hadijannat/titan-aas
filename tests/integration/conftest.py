"""Integration test fixtures using testcontainers.

Provides containerized PostgreSQL and Redis for realistic testing.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Import conditionally to allow unit tests to run without testcontainers
try:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    PostgresContainer = None
    RedisContainer = None


# Skip all integration tests if testcontainers not available
pytestmark = pytest.mark.skipif(
    not TESTCONTAINERS_AVAILABLE,
    reason="testcontainers not installed",
)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start PostgreSQL container for the test session."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Start Redis container for the test session."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Get the database URL for the test container."""
    # testcontainers provides psycopg2 URL, convert to asyncpg
    url = postgres_container.get_connection_url()
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "psycopg2", "asyncpg"
    )


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    """Get the Redis URL for the test container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def db_engine(database_url: str):
    """Create async database engine for tests."""
    from titan.persistence.tables import Base

    engine = create_async_engine(database_url, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables and dispose engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """Create a database session for each test."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def redis_client(redis_url: str):
    """Create a Redis client for tests."""
    import redis.asyncio as redis

    client = redis.from_url(redis_url)
    yield client
    await client.flushdb()  # Clean up after each test
    await client.aclose()


@pytest_asyncio.fixture
async def test_client(
    database_url: str,
    redis_url: str,
    db_engine,
) -> AsyncIterator[AsyncClient]:
    """Create a test client with real database and Redis."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse

    from titan.api.errors import AasApiError, aas_api_exception_handler, generic_exception_handler
    from titan.api.routers import aas_repository, health, submodel_repository, system
    from titan.api.routers import description, discovery, registry, serialization
    from titan.persistence import db as db_module
    from titan.cache import redis as redis_module
    from titan.cache.redis import RedisCache

    import redis.asyncio as aioredis

    # Create a test-specific lifespan that does nothing
    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        yield

    # Create app with test lifespan
    app = FastAPI(
        title="Titan-AAS-Test",
        default_response_class=ORJSONResponse,
        lifespan=test_lifespan,
    )

    # Create test session factory
    test_session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def get_test_session():
        async with test_session_factory() as session:
            yield session

    # Create test redis client
    test_redis = aioredis.from_url(redis_url, decode_responses=False)

    async def get_test_redis():
        return test_redis

    # Create test cache dependency
    async def get_test_cache():
        return RedisCache(test_redis)

    # Override dependencies
    app.dependency_overrides[db_module.get_session] = get_test_session
    app.dependency_overrides[redis_module.get_redis] = get_test_redis
    app.dependency_overrides[aas_repository.get_cache] = get_test_cache
    app.dependency_overrides[submodel_repository.get_cache] = get_test_cache

    # Register exception handlers
    app.add_exception_handler(AasApiError, aas_api_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]

    # Include routers
    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(aas_repository.router)
    app.include_router(submodel_repository.router)
    app.include_router(registry.router)
    app.include_router(discovery.router)
    app.include_router(description.router)
    app.include_router(serialization.router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await test_redis.aclose()
