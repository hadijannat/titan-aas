"""WebSocket API router for real-time events.

Provides WebSocket endpoint for subscribing to AAS/Submodel events.

Clients can subscribe to:
- All events: /events
- Filtered events: /events?entity=aas&identifier=<b64id>

Event payload format:
{
    "eventId": "uuid",
    "eventType": "CREATED|UPDATED|DELETED",
    "entity": "aas|submodel",
    "identifier": "urn:example:...",
    "identifierB64": "dXJuOmV4YW1wbGU6Li4u",
    "timestamp": "2024-01-01T00:00:00Z",
    "etag": "sha256..."
}
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import orjson
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from titan.events import AasEvent, SubmodelEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@dataclass
class Subscription:
    """WebSocket subscription with optional filters."""

    websocket: WebSocket
    entity_filter: str | None = None  # "aas" or "submodel"
    identifier_filter: str | None = None  # Base64URL identifier

    def __hash__(self) -> int:
        """Make Subscription hashable for use in WeakSet."""
        return id(self.websocket)

    def __eq__(self, other: object) -> bool:
        """Compare subscriptions by websocket identity."""
        if not isinstance(other, Subscription):
            return NotImplemented
        return self.websocket is other.websocket


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting."""

    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        entity_filter: str | None = None,
        identifier_filter: str | None = None,
    ) -> Subscription:
        """Accept WebSocket connection and create subscription."""
        await websocket.accept()
        subscription = Subscription(
            websocket=websocket,
            entity_filter=entity_filter,
            identifier_filter=identifier_filter,
        )
        async with self._lock:
            self._subscriptions.add(subscription)
        logger.info(
            f"WebSocket connected (total: {len(self._subscriptions)}, "
            f"filter: entity={entity_filter}, identifier={identifier_filter})"
        )
        return subscription

    async def disconnect(self, subscription: Subscription) -> None:
        """Remove subscription on disconnect."""
        async with self._lock:
            self._subscriptions.discard(subscription)
        logger.info(f"WebSocket disconnected (remaining: {len(self._subscriptions)})")

    async def broadcast_aas_event(self, event: AasEvent) -> None:
        """Broadcast AAS event to matching subscribers."""
        await self._broadcast_event(
            entity="aas",
            identifier_b64=event.identifier_b64,
            payload=self._serialize_aas_event(event),
        )

    async def broadcast_submodel_event(self, event: SubmodelEvent) -> None:
        """Broadcast Submodel event to matching subscribers."""
        await self._broadcast_event(
            entity="submodel",
            identifier_b64=event.identifier_b64,
            payload=self._serialize_submodel_event(event),
        )

    async def _broadcast_event(self, entity: str, identifier_b64: str, payload: bytes) -> None:
        """Broadcast event to matching subscribers."""
        async with self._lock:
            subscriptions = list(self._subscriptions)

        for subscription in subscriptions:
            if self._matches_filter(subscription, entity, identifier_b64):
                try:
                    await subscription.websocket.send_bytes(payload)
                except Exception as e:
                    logger.debug(f"Failed to send to WebSocket: {e}")

    def _matches_filter(self, subscription: Subscription, entity: str, identifier_b64: str) -> bool:
        """Check if event matches subscription filters."""
        if subscription.entity_filter and subscription.entity_filter != entity:
            return False
        if subscription.identifier_filter and subscription.identifier_filter != identifier_b64:
            return False
        return True

    def _serialize_aas_event(self, event: AasEvent) -> bytes:
        """Serialize AAS event to JSON."""
        data: dict[str, Any] = {
            "eventId": event.event_id,
            "eventType": event.event_type.value,
            "entity": event.entity,
            "identifier": event.identifier,
            "identifierB64": event.identifier_b64,
            "timestamp": event.timestamp.isoformat(),
        }
        if event.etag:
            data["etag"] = event.etag
        return orjson.dumps(data)

    def _serialize_submodel_event(self, event: SubmodelEvent) -> bytes:
        """Serialize Submodel event to JSON."""
        data: dict[str, Any] = {
            "eventId": event.event_id,
            "eventType": event.event_type.value,
            "entity": event.entity,
            "identifier": event.identifier,
            "identifierB64": event.identifier_b64,
            "timestamp": event.timestamp.isoformat(),
        }
        if event.etag:
            data["etag"] = event.etag
        return orjson.dumps(data)

    @property
    def connection_count(self) -> int:
        """Get current number of connections."""
        return len(self._subscriptions)


# Global WebSocket manager instance
ws_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    """Get WebSocket manager instance."""
    return ws_manager


@router.websocket("/events")
async def websocket_events(
    websocket: WebSocket,
    entity: str | None = Query(default=None, description="Filter by entity type (aas or submodel)"),
    identifier: str | None = Query(
        default=None, description="Filter by Base64URL encoded identifier"
    ),
) -> None:
    """WebSocket endpoint for real-time AAS/Submodel events.

    Clients can optionally filter events by:
    - entity: "aas" or "submodel"
    - identifier: Base64URL encoded identifier

    Events are sent as JSON messages.
    """
    subscription = await ws_manager.connect(
        websocket,
        entity_filter=entity,
        identifier_filter=identifier,
    )

    try:
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # We don't expect messages from client, but need to handle them
                # to detect disconnects
                message = await websocket.receive_text()
                # Clients can send ping/pong or subscription updates
                if message == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    finally:
        await ws_manager.disconnect(subscription)


class WebSocketEventHandler:
    """Event handler that broadcasts events to WebSocket clients."""

    def __init__(self, manager: WebSocketManager):
        self.manager = manager

    async def handle_aas_event(self, event: AasEvent) -> None:
        """Handle AAS event by broadcasting to WebSocket clients."""
        try:
            await self.manager.broadcast_aas_event(event)
        except Exception as e:
            logger.error(f"Failed to broadcast AAS event: {e}")

    async def handle_submodel_event(self, event: SubmodelEvent) -> None:
        """Handle Submodel event by broadcasting to WebSocket clients."""
        try:
            await self.manager.broadcast_submodel_event(event)
        except Exception as e:
            logger.error(f"Failed to broadcast Submodel event: {e}")
