"""Base class for Titan plugins.

Provides the plugin interface that all plugins must implement:
- Plugin metadata (name, version, description)
- Lifecycle methods (on_load, on_unload)
- Hook registration

Example:
    class MyPlugin(TitanPlugin):
        name = "my-plugin"
        version = "1.0.0"
        description = "Example plugin"

        async def on_load(self) -> None:
            self.register_hook(
                HookType.PRE_CREATE_SHELL,
                self.validate_shell
            )

        async def on_unload(self) -> None:
            pass

        async def validate_shell(self, ctx: HookContext) -> HookResult:
            shell = ctx.get("shell")
            if not shell.id_short:
                return HookResult.abort("idShort is required")
            return HookResult.proceed()
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from titan.plugins.hooks import HookContext, HookResult, HookType

if TYPE_CHECKING:
    from titan.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)

# Type alias for hook handlers
HookHandler = Callable[[HookContext], Awaitable[HookResult]]


class TitanPlugin(ABC):
    """Base class for all Titan plugins.

    Plugins extend this class to add functionality to Titan-AAS.
    Each plugin must define:
    - name: Unique plugin identifier
    - version: Semantic version string
    - on_load: Called when plugin is loaded
    - on_unload: Called when plugin is unloaded

    Plugins can optionally define:
    - description: Human-readable description
    - dependencies: List of required plugins
    - config_schema: Pydantic model for configuration
    """

    # Required metadata
    name: str = ""
    version: str = "0.0.0"

    # Optional metadata
    description: str = ""
    author: str = ""
    dependencies: list[str] = []

    def __init__(self) -> None:
        """Initialize plugin."""
        self._registry: PluginRegistry | None = None
        self._config: dict[str, Any] = {}
        self._hooks: list[tuple[HookType, HookHandler, int]] = []

    @property
    def qualified_name(self) -> str:
        """Full plugin name with version."""
        return f"{self.name}@{self.version}"

    def set_registry(self, registry: "PluginRegistry") -> None:
        """Set the plugin registry (called by loader)."""
        self._registry = registry

    def configure(self, config: dict[str, Any]) -> None:
        """Configure the plugin with runtime settings.

        Args:
            config: Plugin-specific configuration dict
        """
        self._config = config
        logger.debug(f"Plugin {self.name} configured: {config}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self._config.get(key, default)

    @abstractmethod
    async def on_load(self) -> None:
        """Called when the plugin is loaded.

        Use this method to:
        - Register hooks
        - Initialize resources
        - Set up connections
        """
        pass

    @abstractmethod
    async def on_unload(self) -> None:
        """Called when the plugin is unloaded.

        Use this method to:
        - Clean up resources
        - Close connections
        - Deregister any external registrations
        """
        pass

    def register_hook(
        self,
        hook_type: HookType,
        handler: HookHandler,
        priority: int = 0,
    ) -> None:
        """Register a hook handler.

        Args:
            hook_type: Type of hook to register for
            handler: Async function to handle the hook
            priority: Handler priority (higher runs first)
        """
        self._hooks.append((hook_type, handler, priority))
        logger.debug(f"Plugin {self.name} registered hook: {hook_type.name} (priority={priority})")

    def get_registered_hooks(
        self,
    ) -> list[tuple[HookType, HookHandler, int]]:
        """Get all registered hooks for this plugin."""
        return self._hooks.copy()


class NoOpPlugin(TitanPlugin):
    """A no-operation plugin for testing.

    Does nothing but satisfies the plugin interface.
    """

    name = "noop"
    version = "1.0.0"
    description = "No-operation plugin for testing"

    async def on_load(self) -> None:
        """Load (no-op)."""
        pass

    async def on_unload(self) -> None:
        """Unload (no-op)."""
        pass
