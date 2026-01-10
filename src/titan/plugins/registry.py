"""Plugin registry for managing loaded plugins.

The registry maintains:
- Loaded plugins by name
- Hook registrations by type
- Plugin lifecycle management

Example:
    registry = PluginRegistry()

    # Load a plugin
    await registry.load_plugin(MyPlugin())

    # Execute hooks
    result = await registry.execute_hooks(
        HookType.PRE_CREATE_SHELL,
        HookContext(data={"shell": shell})
    )

    # Unload all plugins
    await registry.unload_all()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from titan.plugins.hooks import (
    HookContext,
    HookRegistration,
    HookResult,
    HookResultType,
    HookType,
)

if TYPE_CHECKING:
    from titan.plugins.base import TitanPlugin

logger = logging.getLogger(__name__)


class PluginError(Exception):
    """Base exception for plugin errors."""

    pass


class PluginLoadError(PluginError):
    """Error loading a plugin."""

    pass


class PluginNotFoundError(PluginError):
    """Plugin not found in registry."""

    pass


class PluginRegistry:
    """Registry for managing loaded plugins and hook execution.

    Thread-safe plugin management with:
    - Plugin lifecycle (load/unload)
    - Hook registration and execution
    - Dependency resolution
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._plugins: dict[str, TitanPlugin] = {}
        self._hooks: dict[HookType, list[HookRegistration]] = {
            hook_type: [] for hook_type in HookType
        }
        self._lock = asyncio.Lock()

    @property
    def plugins(self) -> dict[str, TitanPlugin]:
        """Get all loaded plugins (read-only copy)."""
        return dict(self._plugins)

    def get_plugin(self, name: str) -> TitanPlugin | None:
        """Get a loaded plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not loaded
        """
        return self._plugins.get(name)

    def is_loaded(self, name: str) -> bool:
        """Check if a plugin is loaded.

        Args:
            name: Plugin name

        Returns:
            True if plugin is loaded
        """
        return name in self._plugins

    async def load_plugin(
        self,
        plugin: TitanPlugin,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Load a plugin into the registry.

        Args:
            plugin: Plugin instance to load
            config: Optional plugin configuration

        Raises:
            PluginLoadError: If plugin fails to load
        """
        async with self._lock:
            if plugin.name in self._plugins:
                raise PluginLoadError(
                    f"Plugin already loaded: {plugin.name}"
                )

            # Check dependencies
            for dep in plugin.dependencies:
                if dep not in self._plugins:
                    raise PluginLoadError(
                        f"Missing dependency for {plugin.name}: {dep}"
                    )

            # Configure plugin
            plugin.set_registry(self)
            if config:
                plugin.configure(config)

            # Load plugin
            try:
                await plugin.on_load()
            except Exception as e:
                raise PluginLoadError(
                    f"Failed to load plugin {plugin.name}: {e}"
                ) from e

            # Register hooks
            for hook_type, handler, priority in plugin.get_registered_hooks():
                registration = HookRegistration(
                    hook_type=hook_type,
                    plugin=plugin,
                    handler=handler,
                    priority=priority,
                )
                self._hooks[hook_type].append(registration)
                self._hooks[hook_type].sort()  # Sort by priority

            self._plugins[plugin.name] = plugin
            logger.info(f"Loaded plugin: {plugin.qualified_name}")

    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin from the registry.

        Args:
            name: Plugin name to unload

        Raises:
            PluginNotFoundError: If plugin not found
        """
        async with self._lock:
            if name not in self._plugins:
                raise PluginNotFoundError(f"Plugin not loaded: {name}")

            plugin = self._plugins[name]

            # Check if other plugins depend on this one
            for other_name, other_plugin in self._plugins.items():
                if name in other_plugin.dependencies:
                    raise PluginError(
                        f"Cannot unload {name}: "
                        f"{other_name} depends on it"
                    )

            # Remove hook registrations
            for hook_type in HookType:
                self._hooks[hook_type] = [
                    reg
                    for reg in self._hooks[hook_type]
                    if reg.plugin.name != name
                ]

            # Unload plugin
            try:
                await plugin.on_unload()
            except Exception as e:
                logger.error(f"Error unloading plugin {name}: {e}")

            del self._plugins[name]
            logger.info(f"Unloaded plugin: {name}")

    async def unload_all(self) -> None:
        """Unload all plugins in reverse order."""
        # Get names in reverse load order
        names = list(reversed(self._plugins.keys()))

        for name in names:
            try:
                await self.unload_plugin(name)
            except Exception as e:
                logger.error(f"Error unloading plugin {name}: {e}")

    async def execute_hooks(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookResult:
        """Execute all hooks for a given type.

        Hooks are executed in priority order (highest first).
        If any hook aborts, execution stops and abort result is returned.
        If any hook modifies data, the modified data is passed to next hook.

        Args:
            hook_type: Type of hook to execute
            context: Context to pass to hooks

        Returns:
            Combined result from all hooks
        """
        registrations = self._hooks.get(hook_type, [])

        if not registrations:
            return HookResult.proceed()

        for registration in registrations:
            try:
                result = await registration.handler(context)

                if result.result_type == HookResultType.ABORT:
                    logger.debug(
                        f"Hook aborted by {registration.plugin.name}: "
                        f"{result.error_message}"
                    )
                    return result

                if result.result_type == HookResultType.MODIFY:
                    # Update context with modified data
                    if result.data:
                        context.data.update(result.data)

            except Exception as e:
                logger.error(
                    f"Hook error in {registration.plugin.name}: {e}"
                )
                # Continue with other hooks by default
                # Could be configurable to abort on error

        return HookResult.proceed(context.data)

    def get_hook_count(self, hook_type: HookType) -> int:
        """Get number of registered hooks for a type."""
        return len(self._hooks.get(hook_type, []))

    def list_hooks(
        self, hook_type: HookType | None = None
    ) -> list[HookRegistration]:
        """List registered hooks.

        Args:
            hook_type: Filter by type (None for all)

        Returns:
            List of hook registrations
        """
        if hook_type is not None:
            return self._hooks.get(hook_type, []).copy()

        all_hooks: list[HookRegistration] = []
        for hooks in self._hooks.values():
            all_hooks.extend(hooks)
        return all_hooks


# Global registry instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


async def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    if _registry is not None:
        await _registry.unload_all()
    _registry = None
