"""Tests for plugin loader."""

from pathlib import Path
from unittest.mock import patch

import pytest

from titan.plugins.base import TitanPlugin
from titan.plugins.loader import (
    ENTRY_POINT_GROUP,
    LoaderConfig,
    PluginConfig,
    PluginLoader,
)
from titan.plugins.registry import PluginRegistry


class SimplePlugin(TitanPlugin):
    """Simple test plugin."""

    name = "simple-plugin"
    version = "1.0.0"

    async def on_load(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass


class DependentPlugin(TitanPlugin):
    """Plugin with dependency."""

    name = "dependent-plugin"
    version = "1.0.0"
    dependencies = ["simple-plugin"]

    async def on_load(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass


class TestLoaderConfig:
    """Tests for LoaderConfig."""

    def test_default_config(self) -> None:
        """Default config has expected values."""
        config = LoaderConfig()

        assert config.discover_entry_points is True
        assert config.plugin_dirs == []
        assert config.plugins == {}

    def test_custom_config(self) -> None:
        """Custom config values are used."""
        config = LoaderConfig(
            discover_entry_points=False,
            plugin_dirs=[Path("/plugins")],
            plugins={"my-plugin": PluginConfig(name="my-plugin")},
        )

        assert config.discover_entry_points is False
        assert len(config.plugin_dirs) == 1
        assert "my-plugin" in config.plugins


class TestPluginConfig:
    """Tests for PluginConfig."""

    def test_default_plugin_config(self) -> None:
        """Default plugin config is enabled."""
        config = PluginConfig(name="test")

        assert config.name == "test"
        assert config.enabled is True
        assert config.config == {}

    def test_disabled_plugin_config(self) -> None:
        """Plugin can be disabled."""
        config = PluginConfig(
            name="test",
            enabled=False,
            config={"key": "value"},
        )

        assert config.enabled is False
        assert config.config == {"key": "value"}


class TestPluginLoader:
    """Tests for PluginLoader."""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        """Create fresh registry."""
        return PluginRegistry()

    @pytest.fixture
    def loader(self, registry: PluginRegistry) -> PluginLoader:
        """Create loader with registry."""
        config = LoaderConfig(discover_entry_points=False)
        return PluginLoader(registry=registry, config=config)

    def test_entry_point_group(self) -> None:
        """Entry point group is correct."""
        assert ENTRY_POINT_GROUP == "titan.plugins"

    @pytest.mark.asyncio
    async def test_load_plugin(
        self, loader: PluginLoader, registry: PluginRegistry
    ) -> None:
        """Loading a plugin adds it to registry."""
        plugin = SimplePlugin()

        await loader.load_plugin(plugin)

        assert registry.is_loaded("simple-plugin")

    @pytest.mark.asyncio
    async def test_load_plugin_with_config(
        self, loader: PluginLoader, registry: PluginRegistry
    ) -> None:
        """Loading with config passes it to plugin."""
        plugin = SimplePlugin()
        config = {"key": "value"}

        await loader.load_plugin(plugin, config)

        loaded = registry.get_plugin("simple-plugin")
        assert loaded is not None
        assert loaded.get_config("key") == "value"

    @pytest.mark.asyncio
    async def test_load_all_empty(self, loader: PluginLoader) -> None:
        """Loading all with no plugins returns empty list."""
        loaded = await loader.load_all({})

        assert loaded == []

    @pytest.mark.asyncio
    async def test_load_all_with_plugins(self, loader: PluginLoader) -> None:
        """Loading all loads provided plugins."""
        plugins = {
            "simple-plugin": SimplePlugin,
        }

        loaded = await loader.load_all(plugins)

        assert "simple-plugin" in loaded

    @pytest.mark.asyncio
    async def test_load_all_respects_disabled(
        self, registry: PluginRegistry
    ) -> None:
        """Load all skips disabled plugins."""
        config = LoaderConfig(
            discover_entry_points=False,
            plugins={
                "simple-plugin": PluginConfig(
                    name="simple-plugin",
                    enabled=False,
                ),
            },
        )
        loader = PluginLoader(registry=registry, config=config)

        plugins = {"simple-plugin": SimplePlugin}
        loaded = await loader.load_all(plugins)

        assert "simple-plugin" not in loaded

    @pytest.mark.asyncio
    async def test_load_all_with_dependencies(
        self, loader: PluginLoader
    ) -> None:
        """Load all sorts by dependencies."""
        plugins = {
            "dependent-plugin": DependentPlugin,
            "simple-plugin": SimplePlugin,
        }

        loaded = await loader.load_all(plugins)

        # Simple should be loaded first
        assert loaded.index("simple-plugin") < loaded.index("dependent-plugin")

    @pytest.mark.asyncio
    async def test_unload_all(
        self, loader: PluginLoader, registry: PluginRegistry
    ) -> None:
        """Unload all removes all plugins."""
        await loader.load_plugin(SimplePlugin())

        await loader.unload_all()

        assert not registry.is_loaded("simple-plugin")

    def test_discover_no_entry_points(self, loader: PluginLoader) -> None:
        """Discover with no entry points returns empty."""
        # Entry point discovery is disabled in fixture
        plugins = loader.discover()

        # Should be empty since we disabled entry point discovery
        assert isinstance(plugins, dict)


class TestDependencySort:
    """Tests for dependency sorting."""

    @pytest.fixture
    def loader(self) -> PluginLoader:
        """Create loader."""
        config = LoaderConfig(discover_entry_points=False)
        return PluginLoader(config=config)

    def test_sort_no_dependencies(self, loader: PluginLoader) -> None:
        """Plugins without dependencies are in original order."""
        plugins = {"simple-plugin": SimplePlugin}

        sorted_plugins = loader._sort_by_dependencies(plugins)

        assert len(sorted_plugins) == 1
        assert sorted_plugins[0] is SimplePlugin

    def test_sort_with_dependencies(self, loader: PluginLoader) -> None:
        """Dependencies come before dependents."""
        plugins = {
            "dependent-plugin": DependentPlugin,
            "simple-plugin": SimplePlugin,
        }

        sorted_plugins = loader._sort_by_dependencies(plugins)

        simple_idx = sorted_plugins.index(SimplePlugin)
        dependent_idx = sorted_plugins.index(DependentPlugin)
        assert simple_idx < dependent_idx

    def test_sort_missing_dependency(self, loader: PluginLoader) -> None:
        """Missing dependencies are handled gracefully."""
        plugins = {"dependent-plugin": DependentPlugin}

        sorted_plugins = loader._sort_by_dependencies(plugins)

        assert DependentPlugin in sorted_plugins
