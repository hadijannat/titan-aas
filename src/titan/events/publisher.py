"""Event publishing helpers for CRUD operations.

Provides functions to publish events when AAS entities are created, updated, or deleted.
These events are consumed by the WebSocket broadcast handler for real-time updates.

Example:
    from titan.events.publisher import publish_aas_event, publish_aas_deleted

    # After creating/updating an AAS
    await publish_aas_event(event_bus, EventType.CREATED, aas_id, aas_id_b64, doc_bytes, etag)

    # After deleting an AAS
    await publish_aas_deleted(event_bus, aas_id, aas_id_b64)
"""

from __future__ import annotations

from titan.events.bus import EventBus
from titan.events.schemas import (
    AasEvent,
    ConceptDescriptionEvent,
    EventType,
    SubmodelElementEvent,
    SubmodelEvent,
)


async def publish_aas_event(
    event_bus: EventBus,
    event_type: EventType,
    identifier: str,
    identifier_b64: str,
    doc_bytes: bytes,
    etag: str,
) -> AasEvent:
    """Publish an AAS created or updated event.

    Args:
        event_bus: Event bus to publish to
        event_type: CREATED or UPDATED
        identifier: AAS identifier
        identifier_b64: Base64URL-encoded identifier
        doc_bytes: Serialized AAS bytes
        etag: ETag for the AAS

    Returns:
        The published event
    """
    event = AasEvent(
        event_type=event_type,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
    )
    await event_bus.publish(event)
    return event


async def publish_aas_deleted(
    event_bus: EventBus,
    identifier: str,
    identifier_b64: str,
) -> AasEvent:
    """Publish an AAS deleted event.

    Args:
        event_bus: Event bus to publish to
        identifier: AAS identifier
        identifier_b64: Base64URL-encoded identifier

    Returns:
        The published event
    """
    event = AasEvent(
        event_type=EventType.DELETED,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=None,
        etag=None,
    )
    await event_bus.publish(event)
    return event


async def publish_submodel_event(
    event_bus: EventBus,
    event_type: EventType,
    identifier: str,
    identifier_b64: str,
    doc_bytes: bytes,
    etag: str,
    semantic_id: str | None = None,
) -> SubmodelEvent:
    """Publish a Submodel created or updated event.

    Args:
        event_bus: Event bus to publish to
        event_type: CREATED or UPDATED
        identifier: Submodel identifier
        identifier_b64: Base64URL-encoded identifier
        doc_bytes: Serialized Submodel bytes
        etag: ETag for the Submodel
        semantic_id: Optional semantic ID for filtering

    Returns:
        The published event
    """
    event = SubmodelEvent(
        event_type=event_type,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )
    await event_bus.publish(event)
    return event


async def publish_submodel_deleted(
    event_bus: EventBus,
    identifier: str,
    identifier_b64: str,
    semantic_id: str | None = None,
) -> SubmodelEvent:
    """Publish a Submodel deleted event.

    Args:
        event_bus: Event bus to publish to
        identifier: Submodel identifier
        identifier_b64: Base64URL-encoded identifier
        semantic_id: Optional semantic ID for filtering

    Returns:
        The published event
    """
    event = SubmodelEvent(
        event_type=EventType.DELETED,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=None,
        etag=None,
        semantic_id=semantic_id,
    )
    await event_bus.publish(event)
    return event


async def publish_submodel_element_event(
    event_bus: EventBus,
    event_type: EventType,
    submodel_identifier: str,
    submodel_identifier_b64: str,
    id_short_path: str,
    value_bytes: bytes | None = None,
) -> SubmodelElementEvent:
    """Publish a SubmodelElement event.

    Args:
        event_bus: Event bus to publish to
        event_type: CREATED, UPDATED, or DELETED
        submodel_identifier: Parent Submodel identifier
        submodel_identifier_b64: Base64URL-encoded Submodel identifier
        id_short_path: Path to the element (e.g., "Property1" or "Collection1.Property2")
        value_bytes: Serialized element value bytes (None for delete)

    Returns:
        The published event
    """
    event = SubmodelElementEvent(
        event_type=event_type,
        submodel_identifier=submodel_identifier,
        submodel_identifier_b64=submodel_identifier_b64,
        id_short_path=id_short_path,
        value_bytes=value_bytes,
    )
    await event_bus.publish(event)
    return event


async def publish_concept_description_event(
    event_bus: EventBus,
    event_type: EventType,
    identifier: str,
    identifier_b64: str,
    doc_bytes: bytes | None = None,
    etag: str | None = None,
) -> ConceptDescriptionEvent:
    """Publish a ConceptDescription event.

    Args:
        event_bus: Event bus to publish to
        event_type: CREATED, UPDATED, or DELETED
        identifier: ConceptDescription identifier
        identifier_b64: Base64URL-encoded identifier
        doc_bytes: Serialized ConceptDescription bytes (None for delete)
        etag: ETag for the ConceptDescription (None for delete)

    Returns:
        The published event
    """
    event = ConceptDescriptionEvent(
        event_type=event_type,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
    )
    await event_bus.publish(event)
    return event
