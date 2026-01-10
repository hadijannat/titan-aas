"""Plugin system for Titan-AAS extensibility.

Provides a plugin architecture with:
- Plugin base class for custom plugins
- Hook system for intercepting operations
- Plugin discovery via entry points
- Runtime loading and unloading

Example - Creating a plugin:

    from titan.plugins import TitanPlugin, HookType, HookContext, HookResult

    class MyPlugin(TitanPlugin):
        name = "my-plugin"
        version = "1.0.0"

        async def on_load(self) -> None:
            self.register_hook(HookType.PRE_CREATE_SHELL, self.validate)

        async def on_unload(self) -> None:
            pass

        async def validate(self, ctx: HookContext) -> HookResult:
            shell = ctx.get("shell")
            if not shell.id_short:
                return HookResult.abort("idShort is required")
            return HookResult.proceed()

Example - Using plugins in pyproject.toml:

    [project.entry-points."titan.plugins"]
    my_plugin = "my_package:MyPlugin"

Example - Loading plugins:

    from titan.plugins import PluginLoader, get_registry

    loader = PluginLoader()
    plugins = loader.discover()
    await loader.load_all(plugins)

    registry = get_registry()
    result = await registry.execute_hooks(
        HookType.PRE_CREATE_SHELL,
        HookContext(data={"shell": shell})
    )
"""

from titan.plugins.base import HookHandler, NoOpPlugin, TitanPlugin
from titan.plugins.hooks import (
    HOOK_METADATA,
    HookContext,
    HookRegistration,
    HookResult,
    HookResultType,
    HookType,
)
from titan.plugins.loader import (
    ENTRY_POINT_GROUP,
    LoaderConfig,
    PluginConfig,
    PluginLoader,
    load_config_file,
)
from titan.plugins.registry import (
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    PluginRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    # Base
    "TitanPlugin",
    "NoOpPlugin",
    "HookHandler",
    # Hooks
    "HookType",
    "HookContext",
    "HookResult",
    "HookResultType",
    "HookRegistration",
    "HOOK_METADATA",
    # Registry
    "PluginRegistry",
    "PluginError",
    "PluginLoadError",
    "PluginNotFoundError",
    "get_registry",
    "reset_registry",
    # Loader
    "PluginLoader",
    "PluginConfig",
    "LoaderConfig",
    "load_config_file",
    "ENTRY_POINT_GROUP",
]
