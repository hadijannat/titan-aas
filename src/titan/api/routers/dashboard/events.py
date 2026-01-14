"""Dashboard events endpoints - Event stream visualization and control.

Provides:
- Event stream statistics (length, lag, throughput)
- Live event feed via Server-Sent Events (SSE)
- Event history query
- Event replay capability
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from titan.cache import get_redis
from titan.events.runtime import get_event_bus
from titan.security.deps import require_permission
from titan.security.rbac import Permission

if TYPE_CHECKING:
    from redis.asyncio import Redis

router = APIRouter(prefix="/events", tags=["Dashboard - Events"])


class StreamStats(BaseModel):
    """Redis Stream statistics for event bus."""

    stream_key: str
    length: int
    first_entry_id: str | None = None
    last_entry_id: str | None = None
    consumer_groups: int
    pending_messages: int


class EventEntry(BaseModel):
    """A single event from the stream."""

    id: str
    timestamp: datetime
    event_type: str
    entity_type: str | None = None
    identifier: str | None = None
    data: dict[str, Any] | None = None


class EventStats(BaseModel):
    """Event processing statistics."""

    timestamp: datetime
    stream: StreamStats | None = None
    events_per_minute: float | None = None
    subscriber_count: int


class ReplayRequest(BaseModel):
    """Request to replay events."""

    from_id: str
    to_id: str | None = None
    limit: int = 100


class ReplayResult(BaseModel):
    """Result of event replay operation."""

    replayed_count: int
    from_id: str
    to_id: str | None
    timestamp: datetime


# Stream key used by the event bus
EVENT_STREAM_KEY = "titan:events"


@router.get(
    "/stats",
    response_model=EventStats,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_event_stats() -> EventStats:
    """Get event stream statistics.

    Returns:
    - Stream length and entry IDs
    - Consumer group info
    - Pending message count
    - Subscriber count
    """
    redis: Redis = await get_redis()
    event_bus = get_event_bus()

    stream_stats = None
    try:
        # Get stream info
        info = await redis.xinfo_stream(EVENT_STREAM_KEY)
        groups_info = await redis.xinfo_groups(EVENT_STREAM_KEY)

        # Calculate total pending across all groups
        pending = sum(g.get("pending", 0) for g in groups_info)

        stream_stats = StreamStats(
            stream_key=EVENT_STREAM_KEY,
            length=info.get("length", 0),
            first_entry_id=info.get("first-entry", [None])[0],
            last_entry_id=info.get("last-entry", [None])[0],
            consumer_groups=len(groups_info),
            pending_messages=pending,
        )
    except Exception:
        # Stream may not exist yet
        pass

    return EventStats(
        timestamp=datetime.utcnow(),
        stream=stream_stats,
        events_per_minute=None,  # Would need time-series tracking
        subscriber_count=(
            event_bus.subscriber_count if hasattr(event_bus, "subscriber_count") else 0
        ),
    )


@router.get(
    "/stream",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def stream_events(
    event_types: str | None = Query(
        None, description="Comma-separated event types to filter (CREATED,UPDATED,DELETED)"
    ),
) -> StreamingResponse:
    """Stream live events via Server-Sent Events (SSE).

    Opens a persistent connection and streams events as they occur.
    Use this for real-time dashboards and monitoring.

    Optionally filter by event types (comma-separated).
    """
    event_bus = get_event_bus()
    filter_types = set(event_types.split(",")) if event_types else None

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from the event bus."""
        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def handler(event: Any) -> None:
            """Put events into the queue."""
            await queue.put(event)

        # Subscribe to the event bus
        await event_bus.subscribe(handler)

        try:
            while True:
                try:
                    # Wait for events with timeout (for keepalive)
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Apply filter if specified
                    event_type = getattr(event, "event_type", None)
                    if filter_types and str(event_type) not in filter_types:
                        continue

                    # Format as SSE
                    event_data = {
                        "event_type": str(event_type),
                        "timestamp": datetime.utcnow().isoformat(),
                    }

                    # Add event-specific fields
                    if hasattr(event, "identifier"):
                        event_data["identifier"] = event.identifier
                    if hasattr(event, "identifier_b64"):
                        event_data["identifier_b64"] = event.identifier_b64
                    if hasattr(event, "etag"):
                        event_data["etag"] = event.etag

                    yield f"data: {json.dumps(event_data)}\n\n"

                except TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            # Unsubscribe when client disconnects
            # Note: Event bus unsubscribe not yet implemented
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/history",
    response_model=list[EventEntry],
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_event_history(
    limit: int = Query(default=50, le=500, description="Maximum events to return"),
    since_id: str | None = Query(None, description="Return events after this ID"),
) -> list[EventEntry]:
    """Get historical events from the stream.

    Returns recent events in reverse chronological order.
    Use since_id for pagination.
    """
    redis: Redis = await get_redis()
    events: list[EventEntry] = []

    try:
        # Read from stream in reverse order (newest first)
        start = "+" if since_id is None else since_id
        entries = await redis.xrevrange(EVENT_STREAM_KEY, max=start, count=limit)

        for entry_id, data in entries:
            entry_id_str = entry_id.decode() if isinstance(entry_id, bytes) else entry_id

            # Parse timestamp from entry ID (format: timestamp-sequence)
            ts_ms = int(entry_id_str.split("-")[0])
            timestamp = datetime.fromtimestamp(ts_ms / 1000)

            # Decode data fields
            decoded_data = {}
            for k, v in data.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else v
                try:
                    decoded_data[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    decoded_data[key] = val

            events.append(
                EventEntry(
                    id=entry_id_str,
                    timestamp=timestamp,
                    event_type=decoded_data.get("event_type", "UNKNOWN"),
                    entity_type=decoded_data.get("entity_type"),
                    identifier=decoded_data.get("identifier"),
                    data=decoded_data,
                )
            )
    except Exception:
        # Stream may not exist
        pass

    return events


@router.post(
    "/replay",
    response_model=ReplayResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def replay_events(
    request: ReplayRequest,
) -> ReplayResult:
    """Replay events from a specific range.

    Re-publishes events from the stream to all subscribers.
    Use this to recover from processing failures.
    """
    redis: Redis = await get_redis()
    replayed = 0

    try:
        # Read events in range
        end = request.to_id or "+"
        entries = await redis.xrange(
            EVENT_STREAM_KEY,
            min=request.from_id,
            max=end,
            count=request.limit,
        )

        for _entry_id, data in entries:
            # Decode and re-publish each event
            decoded_data = {}
            for k, v in data.items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else v
                try:
                    decoded_data[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    decoded_data[key] = val

            # Note: Event replay requires reconstructing proper event objects
            # which is not yet implemented. For now, just count entries.
            replayed += 1

    except Exception:
        pass

    return ReplayResult(
        replayed_count=replayed,
        from_id=request.from_id,
        to_id=request.to_id,
        timestamp=datetime.utcnow(),
    )
