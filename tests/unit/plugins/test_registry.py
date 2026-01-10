"""Tests for plugin registry."""

import pytest

from titan.plugins.base import TitanPlugin
from titan.plugins.hooks import HookContext, HookResult, HookType
from titan.plugins.registry import (
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    PluginRegistry,
)


class TestPlugin(TitanPlugin):
    """Test plugin implementation."""

    name = "test-plugin"
    version = "1.0.0"
    loaded = False
    unloaded = False

    async def on_load(self) -> None:
        self.loaded = True

    async def on_unload(self) -> None:
        self.unloaded = True


class HookedPlugin(TitanPlugin):
    """Plugin with hooks."""

    name = "hooked-plugin"
    version = "1.0.0"
    hook_called = False

    async def on_load(self) -> None:
        self.register_hook(
            HookType.PRE_CREATE_SHELL,
            self.on_create_shell,
            priority=10,
        )

    async def on_unload(self) -> None:
        pass

    async def on_create_shell(self, ctx: HookContext) -> HookResult:
        self.hook_called = True
        return HookResult.proceed()


class DependentPlugin(TitanPlugin):
    """Plugin with dependencies."""

    name = "dependent-plugin"
    version = "1.0.0"
    dependencies = ["test-plugin"]

    async def on_load(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        """Create fresh registry."""
        return PluginRegistry()

    @pytest.mark.asyncio
    async def test_load_plugin(self, registry: PluginRegistry) -> None:
        """Loading a plugin registers it."""
        plugin = TestPlugin()

        await registry.load_plugin(plugin)

        assert registry.is_loaded("test-plugin")
        assert plugin.loaded is True

    @pytest.mark.asyncio
    async def test_load_duplicate_plugin(self, registry: PluginRegistry) -> None:
        """Loading duplicate plugin raises error."""
        plugin1 = TestPlugin()
        plugin2 = TestPlugin()

        await registry.load_plugin(plugin1)

        with pytest.raises(PluginLoadError, match="already loaded"):
            await registry.load_plugin(plugin2)

    @pytest.mark.asyncio
    async def test_load_with_config(self, registry: PluginRegistry) -> None:
        """Loading with config passes config to plugin."""
        plugin = TestPlugin()
        config = {"key": "value"}

        await registry.load_plugin(plugin, config)

        assert plugin.get_config("key") == "value"

    @pytest.mark.asyncio
    async def test_unload_plugin(self, registry: PluginRegistry) -> None:
        """Unloading a plugin removes it."""
        plugin = TestPlugin()
        await registry.load_plugin(plugin)

        await registry.unload_plugin("test-plugin")

        assert not registry.is_loaded("test-plugin")
        assert plugin.unloaded is True

    @pytest.mark.asyncio
    async def test_unload_nonexistent_plugin(
        self, registry: PluginRegistry
    ) -> None:
        """Unloading non-existent plugin raises error."""
        with pytest.raises(PluginNotFoundError):
            await registry.unload_plugin("nonexistent")

    @pytest.mark.asyncio
    async def test_get_plugin(self, registry: PluginRegistry) -> None:
        """Getting a loaded plugin returns it."""
        plugin = TestPlugin()
        await registry.load_plugin(plugin)

        result = registry.get_plugin("test-plugin")

        assert result is plugin

    @pytest.mark.asyncio
    async def test_get_nonexistent_plugin(
        self, registry: PluginRegistry
    ) -> None:
        """Getting non-existent plugin returns None."""
        result = registry.get_plugin("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_plugins_property(self, registry: PluginRegistry) -> None:
        """Plugins property returns all loaded plugins."""
        plugin = TestPlugin()
        await registry.load_plugin(plugin)

        plugins = registry.plugins

        assert "test-plugin" in plugins
        assert plugins["test-plugin"] is plugin

    @pytest.mark.asyncio
    async def test_load_with_missing_dependency(
        self, registry: PluginRegistry
    ) -> None:
        """Loading plugin with missing dependency raises error."""
        plugin = DependentPlugin()

        with pytest.raises(PluginLoadError, match="Missing dependency"):
            await registry.load_plugin(plugin)

    @pytest.mark.asyncio
    async def test_load_with_satisfied_dependency(
        self, registry: PluginRegistry
    ) -> None:
        """Loading plugin with satisfied dependency succeeds."""
        base = TestPlugin()
        dependent = DependentPlugin()

        await registry.load_plugin(base)
        await registry.load_plugin(dependent)

        assert registry.is_loaded("dependent-plugin")

    @pytest.mark.asyncio
    async def test_unload_with_dependents(
        self, registry: PluginRegistry
    ) -> None:
        """Cannot unload plugin that others depend on."""
        base = TestPlugin()
        dependent = DependentPlugin()

        await registry.load_plugin(base)
        await registry.load_plugin(dependent)

        with pytest.raises(PluginError, match="depends on it"):
            await registry.unload_plugin("test-plugin")

    @pytest.mark.asyncio
    async def test_unload_all(self, registry: PluginRegistry) -> None:
        """Unload all removes all plugins."""
        plugin1 = TestPlugin()
        plugin2 = HookedPlugin()

        await registry.load_plugin(plugin1)
        await registry.load_plugin(plugin2)

        await registry.unload_all()

        assert not registry.is_loaded("test-plugin")
        assert not registry.is_loaded("hooked-plugin")


class TestHookExecution:
    """Tests for hook execution."""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        """Create fresh registry."""
        return PluginRegistry()

    @pytest.mark.asyncio
    async def test_execute_hooks_no_handlers(
        self, registry: PluginRegistry
    ) -> None:
        """Executing hooks with no handlers proceeds."""
        ctx = HookContext(hook_type=HookType.PRE_CREATE_SHELL)

        result = await registry.execute_hooks(HookType.PRE_CREATE_SHELL, ctx)

        assert result.result_type.name == "PROCEED"

    @pytest.mark.asyncio
    async def test_execute_hooks_with_handler(
        self, registry: PluginRegistry
    ) -> None:
        """Executing hooks calls registered handlers."""
        plugin = HookedPlugin()
        await registry.load_plugin(plugin)

        ctx = HookContext(hook_type=HookType.PRE_CREATE_SHELL)
        await registry.execute_hooks(HookType.PRE_CREATE_SHELL, ctx)

        assert plugin.hook_called is True

    @pytest.mark.asyncio
    async def test_hook_abort_stops_execution(
        self, registry: PluginRegistry
    ) -> None:
        """Hook returning abort stops further execution."""

        class AbortPlugin(TitanPlugin):
            name = "abort-plugin"
            version = "1.0.0"

            async def on_load(self) -> None:
                self.register_hook(
                    HookType.PRE_CREATE_SHELL,
                    self.abort_handler,
                )

            async def on_unload(self) -> None:
                pass

            async def abort_handler(self, ctx: HookContext) -> HookResult:
                return HookResult.abort("Not allowed", code=403)

        plugin = AbortPlugin()
        await registry.load_plugin(plugin)

        ctx = HookContext(hook_type=HookType.PRE_CREATE_SHELL)
        result = await registry.execute_hooks(HookType.PRE_CREATE_SHELL, ctx)

        assert result.result_type.name == "ABORT"
        assert result.error_message == "Not allowed"
        assert result.error_code == 403

    @pytest.mark.asyncio
    async def test_hook_modify_updates_context(
        self, registry: PluginRegistry
    ) -> None:
        """Hook returning modify updates context data."""

        class ModifyPlugin(TitanPlugin):
            name = "modify-plugin"
            version = "1.0.0"

            async def on_load(self) -> None:
                self.register_hook(
                    HookType.PRE_CREATE_SHELL,
                    self.modify_handler,
                )

            async def on_unload(self) -> None:
                pass

            async def modify_handler(self, ctx: HookContext) -> HookResult:
                return HookResult.modify({"modified": True})

        plugin = ModifyPlugin()
        await registry.load_plugin(plugin)

        ctx = HookContext(
            hook_type=HookType.PRE_CREATE_SHELL,
            data={"original": True},
        )
        await registry.execute_hooks(HookType.PRE_CREATE_SHELL, ctx)

        assert ctx.data.get("modified") is True

    @pytest.mark.asyncio
    async def test_get_hook_count(self, registry: PluginRegistry) -> None:
        """get_hook_count returns number of registered hooks."""
        plugin = HookedPlugin()
        await registry.load_plugin(plugin)

        count = registry.get_hook_count(HookType.PRE_CREATE_SHELL)

        assert count == 1

    @pytest.mark.asyncio
    async def test_list_hooks(self, registry: PluginRegistry) -> None:
        """list_hooks returns all registrations."""
        plugin = HookedPlugin()
        await registry.load_plugin(plugin)

        hooks = registry.list_hooks(HookType.PRE_CREATE_SHELL)

        assert len(hooks) == 1
        assert hooks[0].plugin is plugin
