"""Hook definitions for plugin system.

Defines hook points that plugins can subscribe to:
- Request lifecycle hooks (pre/post request)
- CRUD operation hooks (pre/post create, update, delete)
- Authentication hooks
- Event hooks

Example:
    @hook(HookType.PRE_CREATE_SHELL)
    async def validate_shell(context: HookContext) -> HookResult:
        shell = context.data["shell"]
        if not shell.id_short:
            return HookResult.abort("idShort is required")
        return HookResult.proceed()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from titan.plugins.base import TitanPlugin


class HookType(Enum):
    """Available hook types for plugin registration."""

    # Request lifecycle
    PRE_REQUEST = auto()
    POST_REQUEST = auto()

    # AAS Shell operations
    PRE_CREATE_SHELL = auto()
    POST_CREATE_SHELL = auto()
    PRE_UPDATE_SHELL = auto()
    POST_UPDATE_SHELL = auto()
    PRE_DELETE_SHELL = auto()
    POST_DELETE_SHELL = auto()

    # Submodel operations
    PRE_CREATE_SUBMODEL = auto()
    POST_CREATE_SUBMODEL = auto()
    PRE_UPDATE_SUBMODEL = auto()
    POST_UPDATE_SUBMODEL = auto()
    PRE_DELETE_SUBMODEL = auto()
    POST_DELETE_SUBMODEL = auto()

    # SubmodelElement operations
    PRE_UPDATE_ELEMENT = auto()
    POST_UPDATE_ELEMENT = auto()

    # Authentication
    PRE_AUTH = auto()
    POST_AUTH = auto()

    # Events
    ON_EVENT = auto()

    # Startup/Shutdown
    ON_STARTUP = auto()
    ON_SHUTDOWN = auto()


class HookResultType(Enum):
    """Result type from hook execution."""

    PROCEED = auto()  # Continue with operation
    ABORT = auto()  # Stop operation, return error
    MODIFY = auto()  # Modify data and continue


@dataclass
class HookResult:
    """Result from hook execution."""

    result_type: HookResultType
    data: dict[str, Any] | None = None
    error_message: str | None = None
    error_code: int | None = None

    @classmethod
    def proceed(cls, data: dict[str, Any] | None = None) -> "HookResult":
        """Continue with operation, optionally with modified data."""
        return cls(result_type=HookResultType.PROCEED, data=data)

    @classmethod
    def abort(cls, message: str, code: int = 400) -> "HookResult":
        """Abort operation with error."""
        return cls(
            result_type=HookResultType.ABORT,
            error_message=message,
            error_code=code,
        )

    @classmethod
    def modify(cls, data: dict[str, Any]) -> "HookResult":
        """Continue with modified data."""
        return cls(result_type=HookResultType.MODIFY, data=data)


@dataclass
class HookContext:
    """Context passed to hook handlers.

    Contains all relevant information for the hook to make decisions.
    """

    hook_type: HookType
    data: dict[str, Any] = field(default_factory=dict)
    request: Any = None  # Optional Request object
    user: Any = None  # Optional User object
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get data value by key."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set data value."""
        self.data[key] = value


@dataclass
class HookRegistration:
    """Registration of a hook handler."""

    hook_type: HookType
    plugin: "TitanPlugin"
    handler: Callable[[HookContext], Awaitable[HookResult]]
    priority: int = 0  # Higher priority runs first

    def __lt__(self, other: "HookRegistration") -> bool:
        """Compare by priority for sorting (higher first)."""
        return self.priority > other.priority


# Hook metadata for documentation
HOOK_METADATA: dict[HookType, dict[str, str]] = {
    HookType.PRE_REQUEST: {
        "description": "Called before processing any request",
        "context": "request, path, method, headers",
    },
    HookType.POST_REQUEST: {
        "description": "Called after processing a request",
        "context": "request, response, duration_ms",
    },
    HookType.PRE_CREATE_SHELL: {
        "description": "Called before creating an AAS shell",
        "context": "shell (AAS model)",
    },
    HookType.POST_CREATE_SHELL: {
        "description": "Called after creating an AAS shell",
        "context": "shell (AAS model), identifier",
    },
    HookType.PRE_UPDATE_SHELL: {
        "description": "Called before updating an AAS shell",
        "context": "shell (AAS model), identifier",
    },
    HookType.POST_UPDATE_SHELL: {
        "description": "Called after updating an AAS shell",
        "context": "shell (AAS model), identifier",
    },
    HookType.PRE_DELETE_SHELL: {
        "description": "Called before deleting an AAS shell",
        "context": "identifier",
    },
    HookType.POST_DELETE_SHELL: {
        "description": "Called after deleting an AAS shell",
        "context": "identifier",
    },
    HookType.PRE_CREATE_SUBMODEL: {
        "description": "Called before creating a submodel",
        "context": "submodel (Submodel model)",
    },
    HookType.POST_CREATE_SUBMODEL: {
        "description": "Called after creating a submodel",
        "context": "submodel (Submodel model), identifier",
    },
    HookType.PRE_UPDATE_SUBMODEL: {
        "description": "Called before updating a submodel",
        "context": "submodel (Submodel model), identifier",
    },
    HookType.POST_UPDATE_SUBMODEL: {
        "description": "Called after updating a submodel",
        "context": "submodel (Submodel model), identifier",
    },
    HookType.PRE_DELETE_SUBMODEL: {
        "description": "Called before deleting a submodel",
        "context": "identifier",
    },
    HookType.POST_DELETE_SUBMODEL: {
        "description": "Called after deleting a submodel",
        "context": "identifier",
    },
    HookType.ON_EVENT: {
        "description": "Called when an event is published",
        "context": "event_type, entity_type, identifier, data",
    },
    HookType.ON_STARTUP: {
        "description": "Called when the application starts",
        "context": "app (FastAPI app)",
    },
    HookType.ON_SHUTDOWN: {
        "description": "Called when the application shuts down",
        "context": "app (FastAPI app)",
    },
}
