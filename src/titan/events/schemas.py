"""Event schemas for Titan-AAS.

Defines typed events for AAS, Submodel, and other entity changes.
Events carry all data needed for the single writer to:
- Persist to database
- Update cache
- Broadcast via MQTT/WebSocket
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class PackageEventType(str, Enum):
    """Type of package event."""

    UPLOADED = "uploaded"
    IMPORTED = "imported"
    EXPORTED = "exported"
    DELETED = "deleted"
    VALIDATED = "validated"
    VERSION_CREATED = "version_created"
    VERSION_ROLLED_BACK = "version_rolled_back"


@dataclass(frozen=True, slots=True)
class PackageEvent:
    """Event for AASX package operations."""

    event_type: PackageEventType
    package_id: str
    filename: str | None = None
    shell_count: int = 0
    submodel_count: int = 0
    content_hash: str | None = None
    import_result: dict | None = None  # For IMPORTED events
    validation_result: dict | None = None  # For VALIDATED events
    # Version-related fields
    version: int | None = None  # Version number for VERSION_CREATED/VERSION_ROLLED_BACK
    parent_package_id: str | None = None  # Previous version ID
    version_comment: str | None = None  # Version description
    created_by: str | None = None  # User who created the version
    rolled_back_from: int | None = None  # Original version for rollbacks
    entity: Literal["package"] = "package"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class OperationInvocationEventType(str, Enum):
    """Type of operation invocation event."""

    INVOKED = "invoked"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class OperationExecutionState(str, Enum):
    """Execution state of an operation invocation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class OperationInvocationEvent:
    """Event for Operation element invocation.

    Emitted when an Operation submodel element is invoked. Downstream connectors
    (OPC-UA, Modbus, HTTP) subscribe to these events and execute the operation.
    """

    event_type: OperationInvocationEventType
    invocation_id: str
    submodel_id: str
    submodel_id_b64: str
    id_short_path: str
    execution_state: OperationExecutionState
    input_arguments: list[dict] | None = None
    output_arguments: list[dict] | None = None
    inoutput_arguments: list[dict] | None = None
    error_message: str | None = None
    error_code: str | None = None
    correlation_id: str | None = None  # For mapping to OPC-UA/Modbus operations
    timeout_ms: int | None = None  # Requested timeout for async operations
    requested_by: str | None = None  # User/service that invoked the operation
    started_at: datetime | None = None  # When execution started
    completed_at: datetime | None = None  # When execution completed
    entity: Literal["operation_invocation"] = "operation_invocation"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# Base event protocol (for type hints)
Event = (
    AasEvent
    | SubmodelEvent
    | SubmodelElementEvent
    | ConceptDescriptionEvent
    | PackageEvent
    | OperationInvocationEvent
)


# Union type for all events
AnyEvent = (
    AasEvent
    | SubmodelEvent
    | SubmodelElementEvent
    | ConceptDescriptionEvent
    | PackageEvent
    | OperationInvocationEvent
)
