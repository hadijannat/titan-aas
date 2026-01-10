"""Integration tests for WebSocket event flow.

Tests the full event flow: API CRUD -> Event Bus -> WebSocket broadcast.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan.api.routers.websocket import WebSocketEventHandler, WebSocketManager
from titan.core.ids import encode_id_to_b64url as encode_id
from titan.events import AnyEvent, InMemoryEventBus
from titan.events.schemas import AasEvent, SubmodelEvent

# Skip if testcontainers not available
pytest.importorskip("testcontainers")


class MockWebSocket:
    """Mock WebSocket for testing event broadcasts."""

    def __init__(self) -> None:
        self.sent_messages: list[bytes] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_bytes(self, data: bytes) -> None:
        self.sent_messages.append(data)


@pytest_asyncio.fixture
async def event_bus() -> AsyncIterator[InMemoryEventBus]:
    """Create and start an in-memory event bus."""
    bus = InMemoryEventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest_asyncio.fixture
async def ws_manager() -> WebSocketManager:
    """Create a WebSocket manager for testing."""
    return WebSocketManager()


@pytest_asyncio.fixture
async def ws_handler(ws_manager: WebSocketManager) -> WebSocketEventHandler:
    """Create a WebSocket event handler."""
    return WebSocketEventHandler(ws_manager)


@pytest_asyncio.fixture
async def event_wired_client(
    database_url: str,
    redis_url: str,
    db_engine,
    event_bus: InMemoryEventBus,
    ws_manager: WebSocketManager,
    ws_handler: WebSocketEventHandler,
) -> AsyncIterator[AsyncClient]:
    """Create a test client with event bus wired to WebSocket handler."""
    from contextlib import asynccontextmanager

    import redis.asyncio as aioredis
    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse

    from titan.api.errors import AasApiError, aas_api_exception_handler, generic_exception_handler
    from titan.api.routers import aas_repository, submodel_repository
    from titan.cache import redis as redis_module
    from titan.cache.redis import RedisCache
    from titan.events import runtime as runtime_module
    from titan.persistence import db as db_module

    # Override the global event bus
    original_bus = runtime_module._event_bus
    runtime_module._event_bus = event_bus

    # Wire handler to event bus
    async def broadcast_handler(event: AnyEvent) -> None:
        if isinstance(event, AasEvent):
            await ws_handler.handle_aas_event(event)
        elif isinstance(event, SubmodelEvent):
            await ws_handler.handle_submodel_event(event)

    await event_bus.subscribe(broadcast_handler)

    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="Titan-AAS-Event-Test",
        default_response_class=ORJSONResponse,
        lifespan=test_lifespan,
    )

    test_session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def get_test_session():
        async with test_session_factory() as session:
            yield session

    test_redis = aioredis.from_url(redis_url, decode_responses=False)

    async def get_test_redis():
        return test_redis

    async def get_test_cache():
        return RedisCache(test_redis)

    app.dependency_overrides[db_module.get_session] = get_test_session
    app.dependency_overrides[redis_module.get_redis] = get_test_redis
    app.dependency_overrides[aas_repository.get_cache] = get_test_cache
    app.dependency_overrides[submodel_repository.get_cache] = get_test_cache

    app.add_exception_handler(AasApiError, aas_api_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]

    app.include_router(aas_repository.router)
    app.include_router(submodel_repository.router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await test_redis.aclose()
    runtime_module._event_bus = original_bus


class TestWebSocketEventFlow:
    """Tests for the complete event flow from API to WebSocket."""

    @pytest.mark.asyncio
    async def test_create_aas_triggers_websocket_event(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Creating an AAS via API should trigger WebSocket event."""
        # Connect a mock WebSocket
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        # Create an AAS via API
        aas = {
            "id": "urn:example:aas:ws-event-test",
            "idShort": "WebSocketEventTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        response = await event_wired_client.post("/shells", json=aas)
        assert response.status_code == 201

        # Wait for event to be processed
        await event_bus.drain()

        # Verify WebSocket received the event
        assert len(mock_ws.sent_messages) == 1
        message = mock_ws.sent_messages[0]
        assert b"created" in message
        assert b"urn:example:aas:ws-event-test" in message

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_update_aas_triggers_websocket_event(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Updating an AAS via API should trigger WebSocket event."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        # Create first
        aas = {
            "id": "urn:example:aas:update-event-test",
            "idShort": "UpdateEventTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        await event_wired_client.post("/shells", json=aas)
        await event_bus.drain()
        mock_ws.sent_messages.clear()  # Clear create event

        # Update
        encoded_id = encode_id(aas["id"])
        updated = {**aas, "idShort": "UpdatedAAS"}
        response = await event_wired_client.put(f"/shells/{encoded_id}", json=updated)
        assert response.status_code in (200, 204)

        await event_bus.drain()

        # Verify WebSocket received update event
        assert len(mock_ws.sent_messages) == 1
        message = mock_ws.sent_messages[0]
        assert b"updated" in message

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_delete_aas_triggers_websocket_event(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Deleting an AAS via API should trigger WebSocket event."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        # Create first
        aas = {
            "id": "urn:example:aas:delete-event-test",
            "idShort": "DeleteEventTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        await event_wired_client.post("/shells", json=aas)
        await event_bus.drain()
        mock_ws.sent_messages.clear()

        # Delete
        encoded_id = encode_id(aas["id"])
        response = await event_wired_client.delete(f"/shells/{encoded_id}")
        assert response.status_code in (200, 204)

        await event_bus.drain()

        # Verify WebSocket received delete event
        assert len(mock_ws.sent_messages) == 1
        message = mock_ws.sent_messages[0]
        assert b"deleted" in message

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_submodel_crud_triggers_websocket_events(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Submodel CRUD operations should trigger WebSocket events."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        # Create submodel
        submodel = {
            "id": "urn:example:submodel:ws-event-test",
            "idShort": "WebSocketEventTestSubmodel",
            "submodelElements": [],
        }
        response = await event_wired_client.post("/submodels", json=submodel)
        assert response.status_code == 201

        await event_bus.drain()

        # Verify WebSocket received the event
        assert len(mock_ws.sent_messages) == 1
        message = mock_ws.sent_messages[0]
        assert b"created" in message
        assert b"submodel" in message

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive_events(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Multiple WebSocket subscribers should all receive events."""
        mock_ws1 = MockWebSocket()
        mock_ws2 = MockWebSocket()
        mock_ws3 = MockWebSocket()

        sub1 = await ws_manager.connect(mock_ws1)
        sub2 = await ws_manager.connect(mock_ws2)
        sub3 = await ws_manager.connect(mock_ws3)

        # Create an AAS
        aas = {
            "id": "urn:example:aas:multi-sub-test",
            "idShort": "MultiSubscriberTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        response = await event_wired_client.post("/shells", json=aas)
        assert response.status_code == 201

        await event_bus.drain()

        # All three should have received the event
        assert len(mock_ws1.sent_messages) == 1
        assert len(mock_ws2.sent_messages) == 1
        assert len(mock_ws3.sent_messages) == 1

        await ws_manager.disconnect(sub1)
        await ws_manager.disconnect(sub2)
        await ws_manager.disconnect(sub3)

    @pytest.mark.asyncio
    async def test_entity_filter_filters_events(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """WebSocket with entity filter should only receive matching events."""
        # Subscribe with AAS filter only
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws, entity_filter="aas")

        # Create a Submodel (should NOT be received)
        submodel = {
            "id": "urn:example:submodel:filtered-out",
            "idShort": "FilteredOutSubmodel",
            "submodelElements": [],
        }
        await event_wired_client.post("/submodels", json=submodel)
        await event_bus.drain()

        # Should NOT have received the submodel event
        assert len(mock_ws.sent_messages) == 0

        # Create an AAS (should be received)
        aas = {
            "id": "urn:example:aas:filtered-in",
            "idShort": "FilteredInAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        await event_wired_client.post("/shells", json=aas)
        await event_bus.drain()

        # Should have received the AAS event
        assert len(mock_ws.sent_messages) == 1

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_disconnected_subscriber_does_not_receive_events(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Disconnected subscribers should not receive events."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        # Disconnect before creating AAS
        await ws_manager.disconnect(subscription)

        # Create an AAS
        aas = {
            "id": "urn:example:aas:no-receive-test",
            "idShort": "NoReceiveTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        await event_wired_client.post("/shells", json=aas)
        await event_bus.drain()

        # Should NOT have received any event
        assert len(mock_ws.sent_messages) == 0


class TestEventPayloadContent:
    """Tests for event payload content and format."""

    @pytest.mark.asyncio
    async def test_event_contains_identifier(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Event payload should contain the entity identifier."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        aas_id = "urn:example:aas:payload-test-123"
        aas = {
            "id": aas_id,
            "idShort": "PayloadTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        await event_wired_client.post("/shells", json=aas)
        await event_bus.drain()

        message = mock_ws.sent_messages[0]
        assert aas_id.encode() in message

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_event_contains_etag(
        self,
        event_wired_client: AsyncClient,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
    ) -> None:
        """Event payload should contain ETag for created/updated events."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        aas = {
            "id": "urn:example:aas:etag-event-test",
            "idShort": "ETagEventTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }
        await event_wired_client.post("/shells", json=aas)
        await event_bus.drain()

        message = mock_ws.sent_messages[0]
        # ETag should be present in the message
        assert b"etag" in message

        await ws_manager.disconnect(subscription)
