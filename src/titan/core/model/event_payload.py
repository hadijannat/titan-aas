"""IDTA-01001 Part 1 v3.0.8: EventPayload for event messaging.

This module defines the EventPayload class used for BasicEventElement
message payloads in event-driven architectures per IDTA-01001-3-0-1_schemasV3.0.8.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel
from titan.core.model.identifiers import ISO8601_UTC_PATTERN, Reference


class EventPayload(StrictModel):
    """Payload for events published by BasicEventElement.

    EventPayload defines the structure of messages exchanged via
    event messaging systems (MQTT, WebSocket, etc.) for AAS events.

    Per IDTA-01001-3-0-1 v3.0.8 JSON Schema:
    - source: Reference to the source of the event (required)
    - observableReference: Reference to the observed element (required)
    - timeStamp: ISO 8601 UTC timestamp of the event (required)
    """

    source: Reference = Field(
        ...,
        description="Reference to the source element that published the event",
    )
    source_semantic_id: Reference | None = Field(
        default=None,
        alias="sourceSemanticId",
        description="Semantic ID of the source element",
    )
    observable_reference: Reference = Field(
        ...,
        alias="observableReference",
        description="Reference to the element being observed",
    )
    observable_semantic_id: Reference | None = Field(
        default=None,
        alias="observableSemanticId",
        description="Semantic ID of the observed element",
    )
    topic: Annotated[str, Field(min_length=1, max_length=255)] | None = Field(
        default=None,
        description="Topic/subject of the event message",
    )
    subject_id: Reference | None = Field(
        default=None,
        alias="subjectId",
        description="Reference to the subject that triggered the event",
    )
    time_stamp: Annotated[str, Field(pattern=ISO8601_UTC_PATTERN)] = Field(
        ...,
        alias="timeStamp",
        description="ISO 8601 UTC timestamp when the event occurred",
    )
    payload: str | None = Field(
        default=None,
        description="Base64-encoded payload data",
    )
