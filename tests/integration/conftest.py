"""Integration test fixtures using Docker.

Provides containerized PostgreSQL and Redis for realistic testing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.integration.docker_utils import DockerService, get_docker_client, run_container


@pytest.fixture(scope="session")
def docker_client():
    """Create a Docker client or skip if Docker is unavailable."""
    try:
        client = get_docker_client()
        client.ping()
    except Exception as exc:
        pytest.skip(f"Docker not available: {exc}")
    yield client
    client.close()


@pytest.fixture(scope="session")
def postgres_container(docker_client) -> Iterator[DockerService]:
    """Start PostgreSQL container for the test session."""
    env = {
        "POSTGRES_USER": "titan",
        "POSTGRES_PASSWORD": "titan",
        "POSTGRES_DB": "titan",
    }
    ports = {"5432/tcp": None}
    with run_container(docker_client, "postgres:16-alpine", env=env, ports=ports) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container(docker_client) -> Iterator[DockerService]:
    """Start Redis container for the test session."""
    ports = {"6379/tcp": None}
    with run_container(docker_client, "redis:7-alpine", ports=ports) as redis:
        yield redis


@pytest.fixture(scope="session")
def event_bus_backend() -> Iterator[None]:
    """Force in-memory event bus for integration tests."""
    from titan.config import settings
    from titan.events import runtime as runtime_module

    original_backend = settings.event_bus_backend
    settings.event_bus_backend = "memory"
    runtime_module._event_bus = None

    yield

    settings.event_bus_backend = original_backend
    runtime_module._event_bus = None


@pytest.fixture(scope="session")
def database_url(postgres_container: DockerService) -> str:
    """Get the database URL for the test container."""
    host = postgres_container.host
    port = postgres_container.port(5432)
    return f"postgresql+asyncpg://titan:titan@{host}:{port}/titan"


@pytest.fixture(scope="session")
def redis_url(redis_container: DockerService) -> str:
    """Get the Redis URL for the test container."""
    host = redis_container.host
    port = redis_container.port(6379)
    return f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def db_engine(database_url: str):
    """Create async database engine for tests."""
    from titan.persistence.tables import Base

    engine = create_async_engine(database_url, echo=False)
    await _wait_for_engine(engine)

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
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def redis_client(redis_url: str):
    """Create a Redis client for tests."""
    import redis.asyncio as redis

    client = redis.from_url(redis_url)
    await _wait_for_redis(client)
    yield client
    await client.flushdb()  # Clean up after each test
    await client.aclose()


@pytest_asyncio.fixture
async def test_client(
    database_url: str,
    redis_url: str,
    db_engine,
    event_bus_backend,
) -> AsyncIterator[AsyncClient]:
    """Create a test client with real database and Redis."""
    from contextlib import asynccontextmanager

    import redis.asyncio as aioredis
    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse

    from titan.api.errors import AasApiError, aas_api_exception_handler, generic_exception_handler
    from titan.api.middleware import CorrelationMiddleware, SecurityHeadersMiddleware
    from titan.api.routers import (
        aas_repository,
        admin,
        concept_description_repository,
        description,
        discovery,
        federation,
        health,
        registry,
        serialization,
        submodel_repository,
        system,
    )
    from titan.cache import redis as redis_module
    from titan.cache.redis import RedisCache
    from titan.config import settings
    from titan.persistence import db as db_module

    original_allow_anonymous = settings.allow_anonymous_admin
    settings.allow_anonymous_admin = True

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

    # Add middleware required by integration tests
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

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
    app.dependency_overrides[concept_description_repository.get_cache] = get_test_cache

    # Register exception handlers
    app.add_exception_handler(AasApiError, aas_api_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]

    # Include routers
    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(admin.router)
    app.include_router(aas_repository.router)
    app.include_router(submodel_repository.router)
    app.include_router(concept_description_repository.router)
    app.include_router(registry.router)
    app.include_router(discovery.router)
    app.include_router(description.router)
    app.include_router(serialization.router)
    app.include_router(federation.router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await test_redis.aclose()
    settings.allow_anonymous_admin = original_allow_anonymous


async def _wait_for_engine(engine, timeout: float = 30.0) -> None:
    """Wait for the database engine to accept connections."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            async with engine.connect():
                return
        except Exception:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.5)


async def _wait_for_redis(client, timeout: float = 30.0) -> None:
    """Wait for Redis to accept connections."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            await client.ping()
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.5)
