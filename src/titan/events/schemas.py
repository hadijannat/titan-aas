"""Event schemas for Titan-AAS.

Defines typed events for AAS, Submodel, and other entity changes.
Events carry all data needed for the single writer to:
- Persist to database
- Update cache
- Broadcast via MQTT/WebSocket
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4


class EventType(str, Enum):
    """Type of entity change event."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class AasEvent:
    """Event for AAS changes."""

    event_type: EventType
    identifier: str
    identifier_b64: str
    doc_bytes: bytes | None = None  # None for delete
    etag: str | None = None
    entity: Literal["aas"] = "aas"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class SubmodelEvent:
    """Event for Submodel changes."""

    event_type: EventType
    identifier: str
    identifier_b64: str
    doc_bytes: bytes | None = None  # None for delete
    etag: str | None = None
    semantic_id: str | None = None
    entity: Literal["submodel"] = "submodel"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class SubmodelElementEvent:
    """Event for SubmodelElement changes.

    Used for $value updates to individual elements.
    """

    event_type: EventType
    submodel_identifier: str
    submodel_identifier_b64: str
    id_short_path: str
    value_bytes: bytes | None = None  # None for delete
    entity: Literal["element"] = "element"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class ConceptDescriptionEvent:
    """Event for ConceptDescription changes."""

    event_type: EventType
    identifier: str
    identifier_b64: str
    doc_bytes: bytes | None = None
    etag: str | None = None
    entity: Literal["concept_description"] = "concept_description"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Base event protocol (for type hints)
Event = AasEvent | SubmodelEvent | SubmodelElementEvent | ConceptDescriptionEvent


# Union type for all events
AnyEvent = AasEvent | SubmodelEvent | SubmodelElementEvent | ConceptDescriptionEvent
