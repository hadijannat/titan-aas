"""Plugin discovery and loading.

Discovers plugins from:
- Python entry points (titan.plugins group)
- Plugin directories
- Direct class references

Example:
    # Load from entry points
    loader = PluginLoader()
    plugins = loader.discover()
    await loader.load_all(plugins)

    # Load specific plugin
    await loader.load_plugin(MyPlugin())

    # Configure from file
    loader.load_config("plugins.yaml")
"""

from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, cast

from titan.plugins.base import TitanPlugin
from titan.plugins.registry import PluginRegistry, get_registry

logger = logging.getLogger(__name__)

# Entry point group for plugin discovery
ENTRY_POINT_GROUP = "titan.plugins"


@dataclass
class PluginConfig:
    """Configuration for a single plugin."""

    name: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoaderConfig:
    """Configuration for the plugin loader."""

    # Entry point discovery
    discover_entry_points: bool = True

    # Directory discovery
    plugin_dirs: list[Path] = field(default_factory=list)

    # Plugin-specific configs
    plugins: dict[str, PluginConfig] = field(default_factory=dict)


class PluginLoader:
    """Discovers and loads plugins into the registry.

    Discovery sources:
    1. Python entry points (titan.plugins group)
    2. Plugin directories (*.py files with TitanPlugin subclasses)
    3. Explicit class references

    Plugins are loaded in dependency order.
    """

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        config: LoaderConfig | None = None,
    ) -> None:
        """Initialize loader.

        Args:
            registry: Plugin registry (uses global if not provided)
            config: Loader configuration
        """
        self.registry = registry or get_registry()
        self.config = config or LoaderConfig()
        self._discovered: dict[str, type[TitanPlugin]] = {}

    def discover(self) -> dict[str, type[TitanPlugin]]:
        """Discover all available plugins.

        Returns:
            Dict mapping plugin names to plugin classes
        """
        self._discovered.clear()

        # Discover from entry points
        if self.config.discover_entry_points:
            self._discover_entry_points()

        # Discover from directories
        for plugin_dir in self.config.plugin_dirs:
            self._discover_directory(plugin_dir)

        logger.info(f"Discovered {len(self._discovered)} plugins: {list(self._discovered.keys())}")
        return self._discovered

    def _discover_entry_points(self) -> None:
        """Discover plugins from entry points."""
        try:
            # Python 3.12+ uses groups parameter
            eps = entry_points(group=ENTRY_POINT_GROUP)

            for ep in eps:
                try:
                    plugin_class = ep.load()
                    if (
                        isinstance(plugin_class, type)
                        and issubclass(plugin_class, TitanPlugin)
                        and plugin_class is not TitanPlugin
                    ):
                        name = getattr(plugin_class, "name", ep.name)
                        self._discovered[name] = plugin_class
                        logger.debug(f"Discovered plugin from entry point: {name}")
                except Exception as e:
                    logger.error(f"Failed to load entry point {ep.name}: {e}")
        except TypeError:
            # Fallback for older Python
            all_eps = entry_points()
            if hasattr(all_eps, "get"):
                eps = cast(Any, all_eps).get(ENTRY_POINT_GROUP, [])
                for ep in eps:
                    try:
                        plugin_class = ep.load()
                        if isinstance(plugin_class, type) and issubclass(plugin_class, TitanPlugin):
                            self._discovered[plugin_class.name] = plugin_class
                    except Exception as e:
                        logger.error(f"Failed to load entry point: {e}")

    def _discover_directory(self, plugin_dir: Path) -> None:
        """Discover plugins from a directory.

        Args:
            plugin_dir: Directory to search for plugins
        """
        if not plugin_dir.exists():
            logger.warning(f"Plugin directory not found: {plugin_dir}")
            return

        # Add directory to path temporarily
        sys.path.insert(0, str(plugin_dir))

        try:
            for py_file in plugin_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                module_name = py_file.stem
                try:
                    module = importlib.import_module(module_name)
                    self._find_plugins_in_module(module)
                except Exception as e:
                    logger.error(f"Failed to import {py_file}: {e}")
        finally:
            sys.path.remove(str(plugin_dir))

    def _find_plugins_in_module(self, module: Any) -> None:
        """Find TitanPlugin subclasses in a module."""
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, TitanPlugin)
                and obj is not TitanPlugin
                and hasattr(obj, "name")
                and obj.name
            ):
                self._discovered[obj.name] = obj
                logger.debug(f"Discovered plugin in module: {obj.name}")

    async def load_all(
        self,
        plugins: dict[str, type[TitanPlugin]] | None = None,
    ) -> list[str]:
        """Load all discovered (or provided) plugins.

        Args:
            plugins: Plugin classes to load (uses discovered if None)

        Returns:
            List of loaded plugin names
        """
        plugins = plugins or self._discovered
        loaded: list[str] = []

        # Sort by dependencies (simple topological sort)
        sorted_plugins = self._sort_by_dependencies(plugins)

        for plugin_class in sorted_plugins:
            name = plugin_class.name

            # Check if enabled in config
            plugin_config = self.config.plugins.get(name)
            if plugin_config and not plugin_config.enabled:
                logger.info(f"Skipping disabled plugin: {name}")
                continue

            try:
                plugin = plugin_class()
                config = plugin_config.config if plugin_config else {}
                await self.registry.load_plugin(plugin, config)
                loaded.append(name)
            except Exception as e:
                logger.error(f"Failed to load plugin {name}: {e}")

        return loaded

    def _sort_by_dependencies(
        self,
        plugins: dict[str, type[TitanPlugin]],
    ) -> list[type[TitanPlugin]]:
        """Sort plugins by dependencies (dependencies first)."""
        result: list[type[TitanPlugin]] = []
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)

            plugin_class = plugins.get(name)
            if plugin_class is None:
                return

            # Visit dependencies first
            for dep in getattr(plugin_class, "dependencies", []):
                visit(dep)

            result.append(plugin_class)

        for name in plugins:
            visit(name)

        return result

    async def load_plugin(
        self,
        plugin: TitanPlugin,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Load a single plugin instance.

        Args:
            plugin: Plugin instance to load
            config: Plugin configuration
        """
        await self.registry.load_plugin(plugin, config)

    async def unload_all(self) -> None:
        """Unload all plugins."""
        await self.registry.unload_all()


def load_config_file(path: Path) -> LoaderConfig:
    """Load plugin configuration from a YAML/JSON file.

    Args:
        path: Path to configuration file

    Returns:
        LoaderConfig instance
    """
    import json

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    content = path.read_text()

    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml

            data = yaml.safe_load(content)
        except ImportError:
            raise ImportError("PyYAML required for YAML config files: pip install pyyaml")
    else:
        data = json.loads(content)

    # Parse configuration
    plugin_configs = {}
    for name, cfg in data.get("plugins", {}).items():
        plugin_configs[name] = PluginConfig(
            name=name,
            enabled=cfg.get("enabled", True),
            config=cfg.get("config", {}),
        )

    return LoaderConfig(
        discover_entry_points=data.get("discover_entry_points", True),
        plugin_dirs=[Path(d) for d in data.get("plugin_dirs", [])],
        plugins=plugin_configs,
    )
